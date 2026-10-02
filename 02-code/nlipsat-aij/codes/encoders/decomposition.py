#!/usr/bin/env python3

import math
from typing import Dict, Any, List, Tuple, Optional
from pysat.formula import IDPool
from pysat.pb import PBEnc


def _fa_clauses(a: int, b: int, cin: int, vpool: IDPool, prefix: str
                ) -> Tuple[int, int, List[List[int]]]:
    """Full adder: (sum, carry, clauses).  sum = a XOR b XOR cin, carry = MAJ(a,b,cin)."""
    s = vpool.id(f'{prefix}_s')
    c = vpool.id(f'{prefix}_c')
    cls = [
        [a, b, cin, -s], [a, -b, -cin, -s], [-a, b, -cin, -s], [-a, -b, cin, -s],
        [-a, -b, -cin, s], [-a, b, cin, s], [a, -b, cin, s], [a, b, -cin, s],
        [-c, a, b], [-c, a, cin], [-c, b, cin],
        [c, -a, -b], [c, -a, -cin], [c, -b, -cin],
    ]
    return s, c, cls


def _ha_clauses(a: int, b: int, vpool: IDPool, prefix: str
                ) -> Tuple[int, int, List[List[int]]]:
    """Half adder: (sum, carry, clauses).  sum = a XOR b, carry = a AND b."""
    s = vpool.id(f'{prefix}_s')
    c = vpool.id(f'{prefix}_c')
    cls = [
        [-a, -b, -s], [a, b, -s], [-a, b, s], [a, -b, s],
        [-c, a], [-c, b], [c, -a, -b],
    ]
    return s, c, cls


def mul(
    a_bits: List[int],
    b_bits: List[int],
    vpool: IDPool,
    prefix: str,
    ub_a: int,
    ub_b: int,
    sense: int = 0
) -> Tuple[List[int], List[List[int]]]:
    num_bits_a = len(a_bits)
    num_bits_b = len(b_bits)

    hard_clauses: List[List[int]] = []

    # Mul-1: partial products z_{ra,rb} <-> a_{ra} AND b_{rb}, grouped by column
    max_col = (num_bits_a - 1) + (num_bits_b - 1)
    columns: List[List[int]] = [[] for _ in range(max_col + 2)]

    for r_a in range(num_bits_a):
        for r_b in range(num_bits_b):
            z = vpool.id(f'{prefix}_z_{r_a}_{r_b}')
            if sense == 0:
                hard_clauses.append([-z, a_bits[r_a]])
                hard_clauses.append([-z, b_bits[r_b]])
                hard_clauses.append([z, -a_bits[r_a], -b_bits[r_b]])
            elif sense == 1:
                hard_clauses.append([-z, a_bits[r_a]])
                hard_clauses.append([-z, b_bits[r_b]])
            elif sense == -1:
                hard_clauses.append([z, -a_bits[r_a], -b_bits[r_b]])
            columns[r_a + r_b].append(z)

    # Mul-2: Wallace-tree reduction of partial-product columns into result bits.
    # Much cheaper than PBEnc.equals (BDD), producing O(n_a * n_b) adder clauses.
    ub_product = ub_a * ub_b
    num_bits_y = max(1, ub_product.bit_length())

    while len(columns) < num_bits_y:
        columns.append([])

    fa_cnt = 0
    for col in range(len(columns)):
        while len(columns[col]) >= 3:
            a, b, cin = columns[col].pop(), columns[col].pop(), columns[col].pop()
            s, cout, cls = _fa_clauses(a, b, cin, vpool, f'{prefix}_fa{col}_{fa_cnt}')
            fa_cnt += 1
            hard_clauses.extend(cls)
            columns[col].append(s)
            if col + 1 >= len(columns):
                columns.append([])
            columns[col + 1].append(cout)

        if len(columns[col]) == 2:
            a, b = columns[col].pop(), columns[col].pop()
            s, cout, cls = _ha_clauses(a, b, vpool, f'{prefix}_ha{col}_{fa_cnt}')
            fa_cnt += 1
            hard_clauses.extend(cls)
            columns[col].append(s)
            if col + 1 >= len(columns):
                columns.append([])
            columns[col + 1].append(cout)

    y_bits: List[int] = []
    for col in range(num_bits_y):
        if col < len(columns) and columns[col]:
            y_bits.append(columns[col][0])
        else:
            y_var = vpool.id(f'{prefix}_y0_{col}')
            hard_clauses.append([-y_var])
            y_bits.append(y_var)

    # Overflow bits beyond num_bits_y must be zero (ub constraint)
    for col in range(num_bits_y, len(columns)):
        for lit in columns[col]:
            hard_clauses.append([-lit])

    return y_bits, hard_clauses

class MulCache:

    def __init__(self, enabled: bool = True):
        self._cache: Dict[tuple, Tuple[List[int], int]] = {}
        self.enabled = enabled
        self.requests = 0
        self.hits = 0
        self.terms = 0

    def get(self, key: tuple) -> Optional[Tuple[List[int], int]]:
        self.requests += 1
        value = self._cache.get(key)
        if value is not None:
            self.hits += 1
        return value

    def put(self, key: tuple, y_bits: List[int], ub_product: int):
        if self.enabled:
            self._cache[key] = (y_bits, ub_product)

    def statistics(self):
        return {'decomposed_terms': self.terms, 'multiplication_requests': self.requests,
                'multiplication_nodes': self.requests - self.hits, 'cache_hits': self.hits}

    @staticmethod
    def make_key(a_bits: List[int], b_bits: List[int], sense: int) -> tuple:
        key_a = tuple(a_bits)
        key_b = tuple(b_bits)
        return (min(key_a, key_b), max(key_a, key_b), sense)

    def __len__(self):
        return len(self._cache)


def mul_cached(
    a_bits: List[int],
    b_bits: List[int],
    vpool: IDPool,
    prefix: str,
    ub_a: int,
    ub_b: int,
    sense: int = 0,
    cache: Optional[MulCache] = None
) -> Tuple[List[int], List[List[int]], int]:
    if cache is not None:
        key = MulCache.make_key(a_bits, b_bits, sense)
        cached = cache.get(key)
        if cached is not None:
            return cached[0], [], cached[1]  # Reuse bits, no new clauses

    y_bits, hard_clauses = mul(a_bits, b_bits, vpool, prefix, ub_a, ub_b, sense)
    ub_product = ub_a * ub_b

    if cache is not None:
        key = MulCache.make_key(a_bits, b_bits, sense)
        cache.put(key, y_bits, ub_product)

    return y_bits, hard_clauses, ub_product

def decompose_sequential(
    omega: List[Tuple[str, int, int, List[int]]],
    vpool: IDPool,
    prefix: str,
    sense: int = 0,
    cache: Optional[MulCache] = None
) -> Tuple[List[int], List[List[int]], int]:
    if len(omega) == 0:
        return [], [], 1

    if len(omega) == 1:
        _, _, ub, bits = omega[0]
        return bits, [], ub

    hard_clauses = []

    _, _, ub1, bits1 = omega[0]
    _, _, ub2, bits2 = omega[1]

    acc_bits, clauses, acc_ub = mul_cached(
        bits1, bits2, vpool, f'{prefix}_mul_1_2', ub1, ub2, sense, cache
    )
    hard_clauses.extend(clauses)

    for k in range(2, len(omega)):
        _, _, ub_k, bits_k = omega[k]
        acc_bits, clauses, acc_ub = mul_cached(
            acc_bits, bits_k, vpool,
            f'{prefix}_mul_1to{k}_and_{k+1}',
            acc_ub, ub_k, sense, cache
        )
        hard_clauses.extend(clauses)

    return acc_bits, hard_clauses, acc_ub

def decompose_binary_tree(
    omega: List[Tuple[str, int, int, List[int]]],
    vpool: IDPool,
    prefix: str,
    sense: int = 0,
    cache: Optional[MulCache] = None
) -> Tuple[List[int], List[List[int]], int]:
    if len(omega) == 0:
        return [], [], 1

    if len(omega) == 1:
        _, _, ub, bits = omega[0]
        return bits, [], ub

    mid = len(omega) // 2
    left = omega[:mid]
    right = omega[mid:]

    left_bits, left_clauses, left_ub = decompose_binary_tree(
        left, vpool, f'{prefix}_L', sense, cache
    )
    right_bits, right_clauses, right_ub = decompose_binary_tree(
        right, vpool, f'{prefix}_R', sense, cache
    )

    result_bits, mul_clauses, result_ub = mul_cached(
        left_bits, right_bits, vpool, f'{prefix}_mul',
        left_ub, right_ub, sense, cache
    )

    all_clauses = left_clauses + right_clauses + mul_clauses
    return result_bits, all_clauses, result_ub

def encode_term_decomp(
    term: Dict[str, Any],
    problem: Dict[str, Any],
    name2idx: Dict[str, int],
    vpool: IDPool,
    prefix: str,
    lb_map: Dict[str, int] = None,
    sense: int = 0,
    strategy: str = "sequential",
    cache: Optional[MulCache] = None
) -> Tuple[Dict[int, Tuple[int, int]], List[List[int]]]:

    term_vars = term.get('vars', {}) or {}
    c = int(term.get('c', 1))

    if not term_vars or c == 0:
        return {}, []

    omega = []
    for var_name, power in sorted(term_vars.items()):
        q = name2idx[var_name]
        ub = int(problem['variables'][var_name]['ub'])
        num_bits = max(1, ub.bit_length())
        bits = [vpool.id(f'x_{q}@{r}') for r in range(num_bits)]

        for _ in range(int(power)):
            omega.append((var_name, q, ub, bits))

    if len(omega) == 0:
        return {}, []

    if cache is not None:
        cache.terms += 1

    if strategy == "binary_tree":
        result_bits, hard_clauses, _ = decompose_binary_tree(
            omega, vpool, prefix, sense, cache
        )
    else:
        result_bits, hard_clauses, _ = decompose_sequential(
            omega, vpool, prefix, sense, cache
        )

    z_mapping = {}
    for r, y_var in enumerate(result_bits):
        weight = c * (2 ** r)
        z_mapping[r] = (y_var, weight)

    return z_mapping, hard_clauses
