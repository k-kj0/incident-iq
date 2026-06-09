# data/synthetic_generator.py  — DROP-IN REPLACEMENT (adds to existing)
import random, itertools, string, json
from typing import List, Dict, Tuple

# ─── 1. CRYPTARITHM GENERATOR (the leaderboard bottleneck) ───────────────────
def generate_cryptarithm() -> Dict:
    """Generate WORD + WORD = WORD style problems with verified solutions."""
    words = [
        ("SEND", "MORE", "MONEY"),
        ("BASE", "BALL", "GAMES"),
        ("EAT",  "THAT", "APPLE"),
        ("ODD",  "ODD",  "EVEN"),
        ("TWO",  "TWO",  "FOUR"),
        ("SIX",  "SIX",  "TEN"),   # may be unsolvable, skip if no sol
        ("GET",  "SET",  "GOLF"),
    ]
    w1, w2, w3 = random.choice(words)
    letters = list(set(w1 + w2 + w3))
    if len(letters) > 10:
        return None

    leading = {w1[0], w2[0], w3[0]}

    def word_val(word, mapping):
        v = 0
        for c in word:
            v = v * 10 + mapping[c]
        return v

    for perm in itertools.permutations(range(10), len(letters)):
        mapping = dict(zip(letters, perm))
        if any(mapping[l] == 0 for l in leading):
            continue
        if word_val(w1, mapping) + word_val(w2, mapping) == word_val(w3, mapping):
            solution = {l: mapping[l] for l in letters}
            answer = word_val(w3, mapping)
            cot = _cryptarithm_cot(w1, w2, w3, solution)
            return {
                "problem": f"Solve the cryptarithm: {w1} + {w2} = {w3}. Each letter represents a unique digit (0-9). What is the value of {w3}?",
                "chain_of_thought": cot,
                "answer": str(answer),
                "type": "cryptarithm",
                "solution_mapping": solution,
            }
    return None

def _cryptarithm_cot(w1, w2, w3, mapping):
    lines = [
        f"We need to assign digits to letters so {w1} + {w2} = {w3}.",
        "Each letter maps to a unique digit; leading letters cannot be 0.",
        "Trying digit assignments systematically:",
    ]
    for l, d in sorted(mapping.items()):
        lines.append(f"  {l} = {d}")
    v1 = sum(mapping[c] * 10**(len(w1)-i-1) for i, c in enumerate(w1))
    v2 = sum(mapping[c] * 10**(len(w2)-i-1) for i, c in enumerate(w2))
    v3 = sum(mapping[c] * 10**(len(w3)-i-1) for i, c in enumerate(w3))
    lines.append(f"Verify: {w1}={v1}, {w2}={v2}, {w3}={v3}. Check: {v1}+{v2}={v1+v2}={v3} ✓")
    return " ".join(lines)


# ─── 2. BIT MANIPULATION GENERATOR ──────────────────────────────────────────
def generate_bit_problem() -> Dict:
    ops = ["AND", "OR", "XOR"]
    a = random.randint(1, 255)
    b = random.randint(1, 255)
    op = random.choice(ops)
    result = {"AND": a & b, "OR": a | b, "XOR": a ^ b}[op]
    cot = (
        f"{a} in binary is {bin(a)}. {b} in binary is {bin(b)}. "
        f"Applying bitwise {op}: {bin(a)} {op} {bin(b)} = {bin(result)}. "
        f"Converting back to decimal: {result}."
    )
    return {
        "problem": f"What is {a} {op} {b} (bitwise operation)?",
        "chain_of_thought": cot,
        "answer": str(result),
        "type": "bit_manipulation",
    }


# ─── 3. SEQUENCE GENERATOR ───────────────────────────────────────────────────
def generate_sequence_problem() -> Dict:
    kind = random.choice(["arithmetic", "geometric", "fibonacci"])
    if kind == "arithmetic":
        start = random.randint(1, 20)
        diff  = random.randint(1, 15)
        seq   = [start + diff * i for i in range(6)]
        cot   = f"Arithmetic sequence. First term={start}, common difference={diff}. Next term={seq[5]}."
    elif kind == "geometric":
        start = random.randint(1, 5)
        ratio = random.randint(2, 4)
        seq   = [start * ratio**i for i in range(6)]
        cot   = f"Geometric sequence. First term={start}, ratio={ratio}. Next term={seq[5]}."
    else:
        a, b = random.randint(1, 5), random.randint(1, 5)
        seq  = [a, b]
        while len(seq) < 6:
            seq.append(seq[-1] + seq[-2])
        cot  = f"Fibonacci-style. a={a}, b={b}. Each term = sum of previous two. Next={seq[5]}."
    shown = seq[:5]
    return {
        "problem": f"What is the next number in the sequence: {', '.join(map(str, shown))}?",
        "chain_of_thought": cot,
        "answer": str(seq[5]),
        "type": "sequence",
    }


# ─── 4. ALGEBRA GENERATOR (keep your existing, this is enhanced) ─────────────
def generate_algebra_problem() -> Dict:
    a = random.randint(1, 20)
    b = random.randint(1, 50)
    x = random.randint(1, 30)
    c = a * x + b
    cot = f"Equation: {a}x + {b} = {c}. Subtract {b}: {a}x = {c-b}. Divide by {a}: x = {x}."
    return {
        "problem": f"Solve for x: {a}x + {b} = {c}",
        "chain_of_thought": cot,
        "answer": str(x),
        "type": "algebra",
    }


# ─── 5. DATASET BUILDER ──────────────────────────────────────────────────────
def format_for_training(sample: Dict) -> Dict:
    """Format with chain-of-thought + \\boxed{} for competition evaluation."""
    return {
        "prompt": f"Solve the following problem step by step.\n\n{sample['problem']}\n\nReasoning:",
        "completion": f" {sample['chain_of_thought']} Therefore, the answer is \\boxed{{{sample['answer']}}}",
        "type": sample["type"],
    }

def build_dataset(n=2000) -> List[Dict]:
    """
    Build balanced dataset.
    Cryptarithm gets 40% weight (leaderboard bottleneck).
    """
    dataset = []
    generators = [
        (generate_cryptarithm,  0.40),
        (generate_bit_problem,  0.20),
        (generate_sequence_problem, 0.20),
        (generate_algebra_problem,  0.20),
    ]
    for _ in range(n * 3):  # oversample to hit target after None filtering
        if len(dataset) >= n:
            break
        gen, weight = random.choices(generators, weights=[g[1] for g in generators])[0], \
                      random.choices(generators, weights=[g[1] for g in generators])[0][1]
        gen = random.choices(generators, weights=[g[1] for g in generators])[0][0]
        sample = gen()
        if sample:
            dataset.append(format_for_training(sample))
    return dataset

if __name__ == "__main__":
    data = build_dataset(500)
    with open("data/training_data.jsonl", "w") as f:
        for row in data:
            f.write(json.dumps(row) + "\n")
    print(f"Generated {len(data)} training examples")
    types = {}
    for r in data:
        types[r["type"]] = types.get(r["type"], 0) + 1
    print("Type distribution:", types)
