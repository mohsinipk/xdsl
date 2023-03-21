from xdsl.ir import Block, BlockArgument, MLContext, Operation, Region
from xdsl.dialects import arith, func, scf, pdl
from xdsl.dialects.builtin import Builtin, ModuleOp
from xdsl.parser import Parser, Source


def test_gen_module():
    assert rewriter_module_1().is_structurally_equivalent(rewriter_module_2())


def input_module():

    b0 = arith.Constant.from_int_and_width(4, 32)
    b1 = arith.Constant.from_int_and_width(2, 32)
    b2 = arith.Addi.get(b0.result, b1.result)
    b3 = func.Return.get(b2.result)

    ir_module = ModuleOp.from_region_or_ops([b0, b1, b2, b3])

    return ir_module


def output_module():

    b0 = arith.Constant.from_int_and_width(4, 32)
    b1 = arith.Constant.from_int_and_width(2, 32)
    b2 = arith.Constant.from_int_and_width(6, 32)
    b3 = func.Return.get(b2.result)

    ir_module = ModuleOp.from_region_or_ops([b0, b1, b2, b3])

    return ir_module


def ir_module():

    b0 = arith.Constant.from_int_and_width(4, 32)
    b1 = arith.Constant.from_int_and_width(2, 32)
    b2 = arith.Constant.from_int_and_width(1, 32)
    b3 = arith.Addi.get(b2.result, b1.result)
    b4 = arith.Addi.get(b3.result, b0.result)
    b5 = func.Return.get(b4.result)

    ir_module = ModuleOp.from_region_or_ops([b0, b1, b2, b3, b4, b5])

    return ir_module


def rewriter_module_1():
    # The rewrite below matches the second addition as root op

    rewrites = """"builtin.module"() ({
  "pdl.pattern"() ({
      %0 = "pdl.operand"() : () -> !pdl.value
      %1 = "pdl.operand"() : () -> !pdl.value
      %2 = "pdl.type"() : () -> !pdl.type
      %3 = "pdl.operation"(%0, %1, %2) {attributeValueNames = [], opName = "arith.addi", operand_segment_sizes = array<i32: 2, 0, 1>} : (!pdl.value, !pdl.value, !pdl.type) -> !pdl.operation
      %4 = "pdl.result"(%3) {index = 0 : i32} : (!pdl.operation) -> !pdl.value
      %5 = "pdl.operand"() : () -> !pdl.value
      %6 = "pdl.operation"(%4, %5, %2) {attributeValueNames = [], opName = "arith.addi", operand_segment_sizes = array<i32: 2, 0, 1>} : (!pdl.value, !pdl.value, !pdl.type) -> !pdl.operation
      "pdl.rewrite"(%6) ({
        %7 = "pdl.operation"(%5, %4, %2) {attributeValueNames = [], opName = "arith.addi", operand_segment_sizes = array<i32: 2, 0, 1>} : (!pdl.value, !pdl.value, !pdl.type) -> !pdl.operation
        "pdl.replace"(%6, %7) {operand_segment_sizes = array<i32: 1, 1, 0>} : (!pdl.operation, !pdl.operation) -> ()
      }) {operand_segment_sizes = array<i32: 1, 0>} : (!pdl.operation) -> ()
    }) {benefit = 2 : i16} : () -> ()
}) : () -> ()
"""

    ctx = MLContext()
    ctx.register_dialect(Builtin)
    ctx.register_dialect(func.Func)
    ctx.register_dialect(arith.Arith)
    ctx.register_dialect(scf.Scf)
    ctx.register_dialect(pdl.PDL)

    pdl_parser = Parser(ctx, rewrites, source=Source.MLIR)
    pdl_module: Operation = pdl_parser.parse_op()

    return pdl_module


def rewriter_module_2():
    # The rewrite below matches the second addition as root op

    rewrites = """"builtin.module"() ({
  "pdl.pattern"() ({
      %0 = "pdl.operand"() : () -> !pdl.value
      %1 = "pdl.operand"() : () -> !pdl.value
      %2 = "pdl.type"() : () -> !pdl.type
      %3 = "pdl.operation"(%0, %1, %2) {attributeValueNames = [], opName = "arith.addi", operand_segment_sizes = array<i32: 2, 0, 1>} : (!pdl.value, !pdl.value, !pdl.type) -> !pdl.operation
      %4 = "pdl.result"(%3) {index = 0 : i32} : (!pdl.operation) -> !pdl.value
      %5 = "pdl.operand"() : () -> !pdl.value
      %6 = "pdl.operation"(%4, %5, %2) {attributeValueNames = [], opName = "arith.addi", operand_segment_sizes = array<i32: 2, 0, 1>} : (!pdl.value, !pdl.value, !pdl.type) -> !pdl.operation
      "pdl.rewrite"(%6) ({
        %7 = "pdl.operation"(%5, %4, %2) {attributeValueNames = [], opName = "arith.addi", operand_segment_sizes = array<i32: 2, 0, 1>} : (!pdl.value, !pdl.value, !pdl.type) -> !pdl.operation
        "pdl.replace"(%6, %7) {operand_segment_sizes = array<i32: 1, 1, 0>} : (!pdl.operation, !pdl.operation) -> ()
      }) {operand_segment_sizes = array<i32: 1, 0>} : (!pdl.operation) -> ()
    }) {benefit = 2 : i16} : () -> ()
}) : () -> ()
"""

    ctx = MLContext()
    ctx.register_dialect(Builtin)
    ctx.register_dialect(func.Func)
    ctx.register_dialect(arith.Arith)
    ctx.register_dialect(scf.Scf)
    ctx.register_dialect(pdl.PDL)

    pdl_parser = Parser(ctx, rewrites, source=Source.MLIR)
    pdl_module: Operation = pdl_parser.parse_op()

    return pdl_module
