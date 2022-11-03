import ast

from dataclasses import dataclass, field
from typing import Any, Dict

from xdsl.frontend.codegen.utils.codegen_function import check_function_signature, get_argument_types, get_return_types
from xdsl.dialects import builtin, func, scf, symref, arith, affine, unimplemented
from xdsl.frontend.codegen.exception import CodegenException
from xdsl.frontend.codegen.inserter import OpInserter
from xdsl.frontend.codegen.type_conversion import TypeHintConverter
from xdsl.ir import Attribute, Operation, Block, Region, SSAValue


@dataclass
class CodegenVisitor(ast.NodeVisitor):
    """Visitor that generates xDSL from the frontend AST."""

    hint_converter: TypeHintConverter = field(init=False)
    """Class responsible for type hint conversion to xDSL types."""

    symbol_table: Dict[str, Attribute] = field(init=False)
    """Symbol table used to query types for symref symbols."""

    inserter: OpInserter = field(init=False)
    """Class responsible for inserting new xDSL ops at the right place."""

    def __init__(self, globals: Dict[str, Any]):
        self.hint_converter = TypeHintConverter(globals)
        self.symbol_table = dict()
        self.inserter = OpInserter()

    def visit(self, node: ast.AST):
        return super().visit(node)

    def generic_visit(self, node: ast.AST):
        raise CodegenException(f"visitor for node {node} does not exist")

    def _cast(self, dst_ty: Attribute, value_ty: Attribute, value: SSAValue | Operation):
        # There are a lot of different casts, for now just put a placeholder op instead
        # of arith.trunci and friends.
        # TODO: implement casts.
        self.inserter.insert_op(unimplemented.Cast.get(value, dst_ty))
        return self.inserter.get_operand()

    def visit_AnnAssign(self, node: ast.AnnAssign):
        """
        Visits type-annotated assignment operation, e.g.

        a: i32 = 3
        """
        # First, find the type of the LHS based on the type hint and create a new
        # symref declaration.
        lhs_ty = self.hint_converter.convert_hint(node.annotation)
        declare_op = symref.Declare.get(node.target.id)
        self.inserter.insert_op(declare_op)

        # Make sure the symbol table knows the type information. For now we only allow
        # referring to the symbols within the function, but in future that should change!
        # TODO: fix symbol table.
        self.symbol_table[node.target.id] = lhs_ty

        # Also, smake sure that we know what type the RHS expression should have.
        # self.state.inferred_type = lhs_ty

        # Next visit RHS and get the value of that expression and its type.
        self.visit(node.value)
        rhs = self.inserter.get_operand()
        rhs_ty = rhs.typ

        # Now, it can be that RHS already used the LHS type, e.g. when visiting
        # a: i32 = 0, constant visitor used the type inferred from the type hint
        # to create 0 constant. ALternatively, it can happen that the type of LHS was
        # not used! For example, if we have x: i32 = 0; y: i64 = x, the type of x
        # is i32 instead of i64, so we must do the type cobersion.
        if lhs_ty != rhs_ty:
            rhs = self._cast(lhs_ty, rhs_ty, rhs)

        update_op = symref.Update.get(node.target.id, rhs)
        self.inserter.insert_op(update_op)
        # self.state.inferred_type = None

    def visit_Assign(self, node: ast.Assign):
        """
        Visits assignment operation, e.g.

        a = 3
        """
        lhs_ty = self.symbol_table[node.targets[0].id]
        # self.state.inferred_type = lhs_ty

        # Get the rhs first.
        self.visit(node.value)
        rhs = self.inserter.get_operand()
        rhs_ty = rhs.typ

        if lhs_ty != rhs_ty:
            rhs = self._cast(lhs_ty, rhs_ty, rhs)

        update_op = symref.Update.get(node.targets[0].id, rhs)
        self.inserter.insert_op(update_op)
        # self.state.inferred_type = None

    def visit_BinOp(self, node: ast.BinOp):
        """
        Visits a binary operation.
        """
        self.visit(node.right)
        rhs = self.inserter.get_operand()
        self.visit(node.left)
        lhs = self.inserter.get_operand()

        # Check if types match.
        if lhs.typ != rhs.typ:
            # If not, it can happen that we should cast either LHS or RHS types. For
            # that, try to reuse the inferred type.
            # if self.state.inferred_type is None:
            #     raise CodegenException(f"types of lhs ({lhs.typ}) and rhs ({rhs.typ}) do not match for binary operator {node.op.__class__.__name__} and cannot be inferred")
            # if self.state.inferred_type == lhs.typ:
            #     rhs = self._cast(lhs.typ, rhs.typ, rhs)
            # elif self.state.inferred_type == rhs.typ:
            #     lhs = self._cast(rhs.typ, lhs.typ, lhs)
            # else:
            raise CodegenException(f"types of lhs ({lhs.typ}) and rhs ({rhs.typ}) do not match for binary operator {node.op.__class__.__name__} and cannot be inferred")

        # TODO: fix this later!
        assert isinstance(lhs.typ, builtin.IntegerType)

        match node.op.__class__.__name__:
            case "Add":
                op = arith.Addi.get(lhs, rhs)
            case "Sub":
                op = arith.Subi.get(lhs, rhs)
            case "Mult":
                op = arith.Muli.get(lhs, rhs)
            case _:
                # TODO: support more operators!
                raise CodegenException(f"binary operator {node.op.__class__.__name__} is not supported")
        self.inserter.insert_op(op)

    def visit_Compare(self, node: ast.Compare):
        # First, opt for a single comparison.
        if len(node.comparators) != 1 and len(node.ops) != 1:
            raise CodegenException(f"require a single comparator and op, found {len(node.comparators)} and {len(node.ops)}")

        op = node.ops[0]
        comp = node.comparators[0]

        # Get the values we compare.
        self.visit(comp)
        rhs = self.inserter.get_operand()
        self.visit(node.left)
        lhs = self.inserter.get_operand()

        # TODO: fix type inference since we infer i1 here and this is wrong!
        if lhs.typ != rhs.typ:
            raise CodegenException(f"types of lhs ({lhs.typ}) and rhs ({rhs.typ}) do not match for compare operator {op.__class__.__name__} and cannot be inferred")

        match op.__class__.__name__:
            case "Eq":
                cmp_op = arith.Cmpi.from_mnemonic(lhs, rhs, "eq")
            case _:
                # TODO: support more comparators!
                raise CodegenException(f"compare operator {op.__class__.__name__} is not supported")

        self.inserter.insert_op(cmp_op)

    def visit_Constant(self, node: ast.Constant):
        """
        Visits a constant value.
        """
        # target_ty = self.state.inferred_type
        # if target_ty is None:
        #     raise CodegenException(f"unable to infer the type of {node.value} on line {node.lineno}")

        # if isinstance(target_ty, builtin.IntegerType):
        #     value_attr = builtin.IntegerAttr.from_int_and_width(node.value, target_ty.width.data)
        # elif isinstance(node.value, builtin.Float32Type):
        #     value_attr = builtin.FloatAttr.from_float_and_width(node.value, 32)
        # elif isinstance(node.value, builtin.Float64Type):
        #     value_attr = builtin.FloatAttr.from_float_and_width(node.value, 64)
        # else:
        #     raise CodegenException(f"trying to infer an unknown type {target_ty} on lin {node.lineno}")
        target_ty = builtin.IntegerType.from_width(32)
        value_attr = builtin.IntegerAttr.from_int_and_width(node.value, target_ty.width.data)
        constant_op = arith.Constant.from_attr(value_attr, target_ty)
        self.inserter.insert_op(constant_op)
        return

    def visit_For(self, node: ast.For):
        if len(node.orelse) > 0:
            raise CodegenException("orelse in for loops is not supported")

        if not isinstance(node.target, ast.Name):
            raise CodegenException("multiple induction variables in for loops is not supported")

        if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
            # Assume all range loops are affine, which in general should be the case?

            # First, proces range arguments.
            args = node.iter.args
            match len(args):
                case 1:
                    self.inserter.insert_op(arith.Constant.from_attr(builtin.IntegerAttr.from_index_int_value(0), builtin.IndexType()))
                    # self.visit(args[0])
                    self.inserter.insert_op(arith.Constant.from_attr(builtin.IntegerAttr.from_index_int_value(0), builtin.IndexType()))
                    self.inserter.insert_op(arith.Constant.from_attr(builtin.IntegerAttr.from_index_int_value(0), builtin.IndexType()))
                case 2:
                    self.visit(args[0])
                    self.visit(args[1])
                    self.inserter.insert_op(arith.Constant.from_attr(1, builtin.IndexType()))
                case 3:
                    self.visit(args[0])
                    self.visit(args[1])
                    self.visit(args[2])
                case _:
                    raise CodegenException(f"expecting 1, 2, or 3 arguments to range function, got {len(args)}")
            # step = self.inserter.get_operand()
            # end = self.inserter.get_operand()
            # start = self.inserter.get_operand()

            # Save previous insertion points.
            prev_insertion_point = self.inserter.ip

            # Visit for loop body.
            for_body_region = Region.from_block_list([Block()])
            self.inserter.set_insertion_point_from_region(for_body_region)
            for stmt in node.body:
                self.visit(stmt)

            op = affine.For.from_region([], 0, 10, for_body_region, 1)
            self.inserter.set_insertion_point_from_block(prev_insertion_point)
            self.inserter.insert_op(op)
            return

        raise CodegenException(f"for loop on line {node.lineno} is not supported")

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """
        Visits a function definition, e.g.

        def foo():
            ...
        """
        # First, check if function signature is valid.
        check_function_signature(node)

        # Then, convert type in the function signature.
        arg_types = get_argument_types(node, self.hint_converter)
        return_types = get_return_types(node, self.hint_converter)

        # Save previous insertion point for declarations.
        prev_declare_insertion_point = self.inserter.declare_ip

        # Create a region for the function body and entry block.
        entry_block = Block()
        body_region = Region.from_block_list([entry_block])
        func_op = func.FuncOp.from_region(node.name, arg_types, return_types, body_region)
        self.inserter.insert_op(func_op)
        self.inserter.set_insertion_point_from_op(func_op)

        # What about globals?
        self.symbol_table = dict()

        # All arguments are declared using symref.
        for i, arg in enumerate(node.args.args):
            symbol_name = arg.arg
            arg = entry_block.insert_arg(arg_types[i], i)
            entry_block.add_op(symref.Declare.get(symbol_name))
            self.symbol_table[symbol_name] = arg_types[i]
            entry_block.add_op(symref.Update.get(symbol_name, arg))

        # Parse function body.
        for stmt in node.body:
            self.visit(stmt)

        self.inserter.set_insertion_point_from_op(func_op.parent_op())
        self.inserter.set_declare_insertion_point(prev_declare_insertion_point)

    def visit_If(self, node: ast.If):
        # Get the condition.
        self.visit(node.test)
        cond = self.inserter.get_operand()
        prev_insertion_point = self.inserter.ip

        # Process true region
        true_region = Region.from_block_list([Block()])
        self.inserter.set_insertion_point_from_region(true_region)
        for stmt in node.body:
            self.visit(stmt)

        # Process false region
        false_region = Region.from_block_list([Block()])
        self.inserter.set_insertion_point_from_region(false_region)
        for stmt in node.orelse:
            self.visit(stmt)

        # Reset insertion point to add scf.if
        self.inserter.set_insertion_point_from_block(prev_insertion_point)
        op = scf.If.get(cond, [], true_region, false_region)
        self.inserter.insert_op(op)

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        # Get the condition.
        self.visit(node.test)
        cond = self.inserter.get_operand()
        prev_insertion_point = self.inserter.ip

        # Process true region
        true_region = Region.from_block_list([Block()])
        self.inserter.set_insertion_point_from_region(true_region)
        self.visit(node.body)
        true_result = self.inserter.get_operand()
        self.inserter.insert_op(scf.Yield.get(true_result))

        # Process false region
        false_region = Region.from_block_list([Block()])
        self.inserter.set_insertion_point_from_region(false_region)
        self.visit(node.orelse)
        false_result = self.inserter.get_operand()
        self.inserter.insert_op(scf.Yield.get(false_result))

        if true_result.typ != false_result.typ:
            raise CodegenException(f"yield types of true region ({true_result.typ}) and false region ({false_result.typ}) do not match for and cannot be inferred")

        # Reset insertion point to add scf.if
        self.inserter.set_insertion_point_from_block(prev_insertion_point)
        op = scf.If.get(cond, [true_result.typ], true_region, false_region)
        self.inserter.insert_op(op)
        self.inserter.set_insertion_point_from_op(op.parent_op())

    def visit_Name(self, node: ast.Name):
        """
        Visits a named variable - can be stack-allocated or an argument.
        """
        # TODO: we should have a proper symbol table!
        ty = self.symbol_table[node.id]
        fetch_op = symref.Fetch.get(node.id, ty)
        self.inserter.insert_op(fetch_op)

    def visit_Return(self, node: ast.Return):
        """
        Visits a return statement in the function.
        """
        if node.value is not None:
            raise CodegenException("returning values from functions is not supported")
        else:
            self.inserter.insert_op(func.Return.get())

    def visit_With(self, node: ast.With):
        """
        Visits a with block which represents a new module.
        """
        module_op = builtin.ModuleOp.from_region_or_ops([])

        # Save previous insertion point for declarations.
        prev_declare_insertion_point = self.inserter.declare_ip

        # Proceed with visitng the module.
        self.inserter.insert_op(module_op)
        self.inserter.set_insertion_point_from_op(module_op)
        for stmt in node.body:
            self.visit(stmt)

        # Reset insertion points back.
        self.inserter.set_insertion_point_from_op(module_op.parent_op())
        self.inserter.set_declare_insertion_point(prev_declare_insertion_point)

    def visit_Pass(self, node: ast.Pass):
        # Do nothing.
        pass