// RUN: mlir-opt %s --mlir-print-op-generic | xdsl-opt -f mlir -t mlir | filecheck %s

"builtin.module"() ({
  "func.func"() ({
  ^0(%0 : memref<?x?xi64>, %1 : memref<?x?xi64>):
    %2 = "arith.constant"() {"value" = 0 : index} : () -> index
    %3 = "arith.constant"() {"value" = 1 : index} : () -> index
    %4 = "memref.dim"(%0, %2) : (memref<?x?xi64>, index) -> index
    %5 = "memref.dim"(%0, %3) : (memref<?x?xi64>, index) -> index
    %6 = "memref.dim"(%1, %2) : (memref<?x?xi64>, index) -> index
    %7 = "memref.dim"(%1, %3) : (memref<?x?xi64>, index) -> index
    %8 = "memref.alloca"(%4, %7) {"alignment" = 0 : i64, "operand_segment_sizes" = array<i32: 2, 0>} : (index, index) -> memref<?x?xi64>
    %9 = "arith.constant"() {"value" = 0 : i64} : () -> i64
    "scf.for"(%2, %4, %3) ({
    ^1(%10 : index):
      "scf.for"(%2, %6, %3) ({
      ^2(%11 : index):
        "memref.store"(%9, %8, %10, %11) : (i64, memref<?x?xi64>, index, index) -> ()
        "scf.for"(%2, %5, %3) ({
        ^3(%12 : index):
          %13 = "memref.load"(%0, %10, %12) : (memref<?x?xi64>, index, index) -> i64
          %14 = "memref.load"(%1, %12, %11) : (memref<?x?xi64>, index, index) -> i64
          %15 = "memref.load"(%8, %10, %11) : (memref<?x?xi64>, index, index) -> i64
          %16 = "arith.muli"(%13, %14) : (i64, i64) -> i64
          %17 = "arith.addi"(%15, %16) : (i64, i64) -> i64
          "memref.store"(%17, %8, %10, %11) : (i64, memref<?x?xi64>, index, index) -> ()
          "scf.yield"() : () -> ()
        }) : (index, index, index) -> ()
        "scf.yield"() : () -> ()
      }) : (index, index, index) -> ()
      "scf.yield"() : () -> ()
    }) : (index, index, index) -> ()
    "func.return"(%8) : (memref<?x?xi64>) -> ()
  }) {"sym_name" = "matmul", "function_type" = (memref<?x?xi64>, memref<?x?xi64>) -> memref<?x?xi64>, "sym_visibility" = "private"} : () -> ()
}) : () -> ()

// CHECK: "builtin.module"() ({
// CHECK-NEXT:   "func.func"() ({
// CHECK-NEXT:   ^0(%0 : memref<?x?xi64>, %1 : memref<?x?xi64>):
// CHECK-NEXT:     %2 = "arith.constant"() {"value" = 0 : index} : () -> index
// CHECK-NEXT:     %3 = "arith.constant"() {"value" = 1 : index} : () -> index
// CHECK-NEXT:     %4 = "memref.dim"(%0, %2) : (memref<?x?xi64>, index) -> index
// CHECK-NEXT:     %5 = "memref.dim"(%0, %3) : (memref<?x?xi64>, index) -> index
// CHECK-NEXT:     %6 = "memref.dim"(%1, %2) : (memref<?x?xi64>, index) -> index
// CHECK-NEXT:     %7 = "memref.dim"(%1, %3) : (memref<?x?xi64>, index) -> index
// CHECK-NEXT:     %8 = "memref.alloca"(%4, %7) {"alignment" = 0 : i64, "operand_segment_sizes" = array<i32: 2, 0>} : (index, index) -> memref<?x?xi64>
// CHECK-NEXT:     %9 = "arith.constant"() {"value" = 0 : i64} : () -> i64
// CHECK-NEXT:     "scf.for"(%2, %4, %3) ({
// CHECK-NEXT:     ^1(%10 : index):
// CHECK-NEXT:       "scf.for"(%2, %6, %3) ({
// CHECK-NEXT:       ^2(%11 : index):
// CHECK-NEXT:         "memref.store"(%9, %8, %10, %11) : (i64, memref<?x?xi64>, index, index) -> ()
// CHECK-NEXT:         "scf.for"(%2, %5, %3) ({
// CHECK-NEXT:         ^3(%12 : index):
// CHECK-NEXT:           %13 = "memref.load"(%0, %10, %12) : (memref<?x?xi64>, index, index) -> i64
// CHECK-NEXT:           %14 = "memref.load"(%1, %12, %11) : (memref<?x?xi64>, index, index) -> i64
// CHECK-NEXT:           %15 = "memref.load"(%8, %10, %11) : (memref<?x?xi64>, index, index) -> i64
// CHECK-NEXT:           %16 = "arith.muli"(%13, %14) : (i64, i64) -> i64
// CHECK-NEXT:           %17 = "arith.addi"(%15, %16) : (i64, i64) -> i64
// CHECK-NEXT:           "memref.store"(%17, %8, %10, %11) : (i64, memref<?x?xi64>, index, index) -> ()
// CHECK-NEXT:           "scf.yield"() : () -> ()
// CHECK-NEXT:         }) : (index, index, index) -> ()
// CHECK-NEXT:         "scf.yield"() : () -> ()
// CHECK-NEXT:       }) : (index, index, index) -> ()
// CHECK-NEXT:       "scf.yield"() : () -> ()
// CHECK-NEXT:     }) : (index, index, index) -> ()
// CHECK-NEXT:     "func.return"(%8) : (memref<?x?xi64>) -> ()
// CHECK-NEXT:   }) {"function_type" = (memref<?x?xi64>, memref<?x?xi64>) -> memref<?x?xi64>, "sym_name" = "matmul", "sym_visibility" = "private"} : () -> ()
// CHECK-NEXT: }) : () -> ()