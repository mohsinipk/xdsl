import ast
import xdsl.dialects.builtin as builtin

from dataclasses import dataclass, field
from typing import _GenericAlias, Any, Dict, List, Optional, Type
from xdsl.frontend.dialects.builtin import Float32Type, FrontendType, TensorType, IntegerType
from xdsl.ir import Attribute


@dataclass
class TypeHintConversionException(Exception):
    """
    Exception type if type hint conversion failed or is not supported.
    """
    msg: str

    def __str__(self) -> str:
        return f"Conversion of type hint failed with: {self.msg}."


@dataclass
class TypeHintConverter:
    """
    Class responsible for conversion of Python type hints to concrete xDSL
    types.
    """

    globals: Dict[str, Any]
    """Stores all globals in the current Python program, including imports."""

    type_cache: Dict[str, Attribute] = field(default_factory=dict)
    """Cache for xDSL types created so far to avoid repeated conversions."""

    type_backward_map: Dict[Attribute, FrontendType] = field(default_factory=dict)
    """backward map to get frontend types from xDSL type."""

    def _convert_subscript(self, hint: ast.Subscript) -> Attribute:
        ty_name = hint.value.id
        ty = self.globals[ty_name]

        # TODO: this should also be defined by the frontend program.
        if ty_name == "List":
            # This is a dynamically sized tensor!
            num_dims = 1
            node = hint.slice
            while isinstance(node, ast.Subscript):
                num_dims += 1
                node = node.slice

            assert isinstance(node, ast.Name)
            el_ty = self._convert_name(node)
            xdsl_ty = builtin.TensorType.from_type_and_list(el_ty, [-1 for d in range(num_dims)])
            if xdsl_ty.__class__ not in self.type_backward_map:
                    self.type_backward_map[xdsl_ty.__class__] = TensorType
            return xdsl_ty


        # Any type hint must be a frontend type.
        if issubclass(ty, FrontendType):
            if isinstance(hint.slice, ast.Tuple):
                args = []
                for ty_arg in hint.slice.elts:
                    if isinstance(ty_arg, ast.Name):
                        xdsl_ty = self._convert_name(ty_arg)
                        args.append(xdsl_ty)
                    elif isinstance(ty_arg, ast.Subscript):
                        
                        # TODO: fix this porperly, but it should be shape!
                        ty_args = ty_arg.slice
                        res = []
                        if isinstance(ty_args, ast.Tuple):
                            for ty_arg in ty_args.elts:
                                if isinstance(ty_arg.slice, ast.UnaryOp):
                                    op_name = ty_arg.slice.op.__class__.__name__
                                    if op_name == "USub":
                                        # TODO: This is a dynamic shape! But we should implement this properly.
                                        assert int(ty_arg.slice.operand.value) == 1
                                        v = -int(ty_arg.slice.operand.value)
                                else:
                                    v = int(ty_arg.slice.value)
                                res.append(v)
                        args.append(res)
                    else:
                        msg = f"expected 'Name' or 'Subscript', got {ty_arg.__name__}"
                        raise TypeHintConversionException(msg)
                
                xdsl_ty = ty.to_xdsl()(*args)
                if xdsl_ty.__class__ not in self.type_backward_map:
                    self.type_backward_map[xdsl_ty.__class__] = ty
                return xdsl_ty

            elif isinstance(hint.slice, ast.Name):
                xdsl_ty = ty.to_xdsl()(self._convert_name(hint.slice))
                if xdsl_ty.__class__ not in self.type_backward_map:
                    self.type_backward_map[xdsl_ty.__class__] = ty
                return xdsl_ty
            else:
                msg = f"expected 'Tuple', got {hint.slice}"
                raise TypeHintConversionException(msg)

        # Otherwise abort.
        msg = f"expected a sublcass of FrontendType, got {hint.slice}"
        raise TypeHintConversionException(msg)

    def _convert_name(self, hint: ast.Name) -> Attribute:
        # First, check if we have already converted this type hint.
        ty_name: str = hint.id
        if ty_name in self.type_cache:
            return self.type_cache[ty_name]

        # TODO: move this to frontend program so that we can associate types and have them in cache already!
        # TODO: index can be builtin as well?
        if ty_name == "int":
            xdsl_ty = builtin.IntegerType.from_width(64)
            if xdsl_ty.__class__ not in self.type_backward_map:
                self.type_backward_map[xdsl_ty.__class__] = IntegerType
            return xdsl_ty
        if ty_name == "float":
            xdsl_ty = builtin.Float32Type()
            if xdsl_ty.__class__ not in self.type_backward_map:
                self.type_backward_map[xdsl_ty.__class__] = Float32Type
            return xdsl_ty
        if ty_name == "bool":
            xdsl_ty = builtin.IntegerType.from_width(1)
            if xdsl_ty.__class__ not in self.type_backward_map:
                self.type_backward_map[xdsl_ty.__class__] = IntegerType
            return xdsl_ty

        # Otherwise, we should get the class from imports based on the type
        # name.
        ty = self.globals[ty_name]

        # If the type is a generic type, go through the type arguments and
        # materialize them. For example, it can be
        # 
        #   class IntType(Generic[W], FrontendType)
        if isinstance(ty, _GenericAlias):
            args = []
            for ty_arg in ty.__args__:

                # Supporting simple cases like Literal[3] is sufficient for
                # now.
                if len(ty_arg.__args__) != 1 and not isinstance(ty_arg.__args__[0], int):
                    raise TypeHintConversionException(f"expected a single integer type \
                                                        argument, got {ty_arg.__args__}")
                args.append(ty_arg.__args__[0])

            # Finally, get the constructor of this type and build an xDSL type.
            if issubclass(ty.__origin__, FrontendType):
                constructor = ty.to_xdsl()
                xdsl_ty = constructor(*args)
                if xdsl_ty.__class__ not in self.type_backward_map:
                    self.type_backward_map[xdsl_ty.__class__] = ty.__origin__
                return xdsl_ty

            msg = f"expected a sublcass of FrontendType, got {ty.__origin__.__name__}"
            raise TypeHintConversionException(msg)

        # Otherwise, it can be a class from the frontend, e.g class IndexType(FrontendType).
        if issubclass(ty, FrontendType):
            xdsl_ty = ty.to_xdsl()()
            if xdsl_ty.__class__ not in self.type_backward_map:
                self.type_backward_map[xdsl_ty.__class__] = ty
            return xdsl_ty

        # Otherwise, abort.
        # TODO: while this is enough to support simple integer types, we should
        # support other corner cases as well.
        raise TypeHintConversionException(f"unsupported hint of type {ty}")

    def convert_hint(self, hint: Type) -> Optional[Attribute]:
        """handles all type hint conversions."""

        # Type hint can be not provided, e.g. when returning None from the
        # function implicitly. Then simply return None and the caller should
        # decide what to do next.
        if hint is None:
            return None

        # In general, any type hint is a Subscript AST node, for example
        # Foo[Literal[2]].
        if isinstance(hint, ast.Subscript):
            return self._convert_subscript(hint)

        # Type hint can also be a TypeAlias, which we support. For example, one
        # can define foo = Foo[Literal[2]].
        if isinstance(hint, ast.Name):
            return self._convert_name(hint)

        # In all other cases, abort.
        raise TypeHintConversionException(f"unknown hint of type {type(hint)}")