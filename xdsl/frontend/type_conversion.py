import ast
import xdsl.dialects.builtin as xdsl_builtin
import xdsl.frontend.dialects.builtin as frontend_builtin

from dataclasses import dataclass, field
from typing import Any, Dict, _GenericAlias, Type, TypeAlias  # type: ignore
from xdsl.frontend.dialects.builtin import _FrontendType
from xdsl.frontend.exception import CodeGenerationException
from xdsl.ir import Attribute

TypeName: TypeAlias = str


@dataclass
class TypeConverter:
    """
    Class responsible for conversion of Python type hints to concrete xDSL
    types.
    """

    globals: Dict[str, Any]
    """
    Stores all globals in the current Python program, including imports. This is
    useful because we can lookup a class which corresponds to the type
    annotation without explicitly constructing it.
    """

    name_to_xdsl_type_map: Dict[TypeName,
                                Attribute] = field(default_factory=dict)
    """
    Map to cache xDSL types created so far to avoid repeated conversions.
    """

    xdsl_to_frontend_type_map: Dict[Type[Attribute],
                                    Type[_FrontendType]] = field(
                                        default_factory=dict)
    """
    Map to lookup frontend types based on xDSL type. Useful if we want to see
    what overloaded Python operations does this xDSL type support.
    """

    def __post_init__(self) -> None:
        # Cache index type because it is always used implicitly in loops and
        # many other IR constructs.
        self._cache_type(frontend_builtin._Index, xdsl_builtin.IndexType(),
                         "index")

    def _cache_type(self, frontend_type: Type[_FrontendType],
                    xdsl_type: Attribute, type_name: TypeName) -> None:
        """Records frontend and corresponding xDSL types in cache."""
        if type_name not in self.name_to_xdsl_type_map:
            self.name_to_xdsl_type_map[type_name] = xdsl_type
        if xdsl_type.__class__ not in self.xdsl_to_frontend_type_map:
            self.xdsl_to_frontend_type_map[xdsl_type.__class__] = frontend_type

    def _convert_name(self, type_hint: ast.Name) -> Attribute:
        # First, check if we have already converted this type hint.
        type_name = type_hint.id
        if type_name in self.name_to_xdsl_type_map:
            return self.name_to_xdsl_type_map[type_name]

        # Otherwise, it must be some frontend type, and we can look up its class
        # using the imports.
        type_class = self.globals[type_name]

        # First, type can be generic, e.g. `class _Integer(Generic[_W, _S])`.
        if isinstance(type_class, _GenericAlias):
            generic_type_arguments = type_class.__args__
            arguments_for_constructor = []
            for type_argument in generic_type_arguments:

                # Convert Literal[...] to concrete values.
                materialized_arguments = type_argument.__args__
                if len(materialized_arguments) != 1:
                    raise CodeGenerationException(
                        type_hint.lineno, type_hint.col_offset,
                        f"Expected 1 type argument for generic type '{type_name}', got {len(materialized_arguments)} type arguments instead."
                    )
                arguments_for_constructor.append(materialized_arguments[0])
                continue

            # Finally, get the constructor of this type and build an xDSL type.
            if issubclass(type_class.__origin__, _FrontendType):
                xdsl_type = type_class.to_xdsl()(*arguments_for_constructor)
                self._cache_type(type_class.__origin__, xdsl_type, type_name)
                return xdsl_type

            # If this is not a subclass of FrontendType, then abort.
            raise CodeGenerationException(
                type_hint.lineno, type_hint.col_offset,
                f"Expected a sublcass of 'FrontendType', got {type_class.__origin__.__name__}."
            )

        # Otherwise, type can be a simple non-generic frontend type, e.g. `class
        # _Index(FrontendType)`.
        if issubclass(type_class, _FrontendType):
            xdsl_type = type_class.to_xdsl()()
            self._cache_type(type_class, xdsl_type, type_name)
            return xdsl_type

        raise CodeGenerationException(
            type_hint.lineno, type_hint.col_offset,
            f"Unknown type hint for type '{type_name}' inside 'ast.Name' expression."
        )

    def convert_type_hint(self, type_hint: ast.expr) -> Attribute:
        """Convertes a Python/frontend type given as AST expression into xDSL type."""

        # Type hint should always be provided if this function is called.
        assert type_hint is not None

        # TODO: Type hint can be a Subscript AST node, for example
        # `Foo[Literal[2]]``. Support this in the future patches.
        if isinstance(type_hint, ast.Subscript):
            raise CodeGenerationException(
                type_hint.lineno, type_hint.col_offset,
                f"Converting subscript type hints is not supported.")

        # Type hint can also be a TypeAlias. For example, one can define
        # `foo = Foo[Literal[2]]`. This case also handles standard Python types, like
        # int, float, etc.
        if isinstance(type_hint, ast.Name):
            return self._convert_name(type_hint)

        raise CodeGenerationException(
            type_hint.lineno, type_hint.col_offset,
            f"Unknown type hint AST node '{type_hint}'.")