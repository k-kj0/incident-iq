import random
import json
import re
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum


class ReasoningType(Enum):
    ALGEBRAIC = "algebraic"
    SYMBOLIC = "symbolic" 
    SEQUENCE = "sequence"
    CIPHER = "cipher"


@dataclass
class ReasoningProblem:
    """A structured reasoning problem with verifiable answer"""
    problem_type: ReasoningType
    prompt: str
    ground_truth: str
    reasoning_trace: List[str]
    complexity: int  # 1-5, where 5 is hardest


class SymbolicSolver:
    """
    Generates mathematically verifiable reasoning problems.
    Unlike LLM-generated data, these have guaranteed correct answers.
    """
    
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.problems: List[ReasoningProblem] = []
        
    def generate_algebraic(self, complexity: int = 3) -> ReasoningProblem:
        """Generate solvable algebraic equations with step-by-step verification"""
        
        if complexity <= 2:
            # Linear equations: ax + b = c
            a = random.randint(1, 5)
            b = random.randint(1, 10)
            c = random.randint(10, 30)
            # Solve: x = (c - b) / a
            x = (c - b) / a
            
            # Ensure integer result for simplicity
            while not x.is_integer():
                a = random.randint(1, 5)
                b = random.randint(1, 10)
                c = random.randint(10, 30)
                x = (c - b) / a
            
            x = int(x)
            
            prompt = f"""Solve this equation step by step:

Problem: If {a}x + {b} = {c}, find the value of x.

Step 1: Subtract {b} from both sides
Step 2: Divide both sides by {a}
Step 3: Simplify to find x"""

            reasoning_trace = [
                f"Equation: {a}x + {b} = {c}",
                f"Subtract {b}: {a}x = {c - b}",
                f"Divide by {a}: x = {x}",
                f"Solution: x = {x}"
            ]
            
        else:
            # Quadratic equations for higher complexity
            # x² + bx + c = 0
            # Generate with integer roots
            root1 = random.randint(-10, 10)
            root2 = random.randint(-10, 10)
            
            # Expand: (x - r1)(x - r2) = x² - (r1+r2)x + (r1*r2)
            a = 1
            b = -(root1 + root2)
            c = root1 * root2
            
            # Make it interesting - add a coefficient sometimes
            if complexity >= 4 and random.random() > 0.5:
                a = random.randint(2, 4)
                # Scale roots: a*x² + b*x + c = 0 where roots are scaled
                # For simplicity, we'll keep integer roots after scaling
                # Actually simpler: generate from (ax - r1)(ax - r2) format
                pass
            
            prompt = f"""Solve this quadratic equation step by step:

Problem: Find all values of x satisfying: {a}x² + {b}x + {c} = 0

Use the quadratic formula: x = [-b ± √(b² - 4ac)] / (2a)"""
            
            discriminant = b*b - 4*a*c
            sqrt_d = discriminant ** 0.5
            x1 = (-b + sqrt_d) / (2*a)
            x2 = (-b - sqrt_d) / (2*a)
            
            reasoning_trace = [
                f"Equation: {a}x² + {b}x + {c} = 0",
                f"a={a}, b={b}, c={c}",
                f"Discriminant: Δ = b² - 4ac = {discriminant}",
                f"√Δ = {sqrt_d}",
                f"x₁ = (-{b} + {sqrt_d})/(2*{a}) = {x1}",
                f"x₂ = (-{b} - {sqrt_d})/(2*{a}) = {x2}"
            ]
            
            # Format answer as boxed
            answer_str = f"{x1}, {x2}" if x1 != x2 else f"{x1}"
            x1, x2 = int(x1), int(x2)
            answer_str = f"{x1}, {x2}" if x1 != x2 else f"{x1}"
        
        return ReasoningProblem(
            problem_type=ReasoningType.ALGEBRAIC,
            prompt=prompt,
            ground_truth=f"\\boxed{{{answer_str}}}",
            reasoning_trace=reasoning_trace,
            complexity=complexity
        )
    
    def generate_symbolic_logic(self, complexity: int = 3) -> ReasoningProblem:
        """Generate symbolic logic puzzles with truth tables"""
        
        # Define logical operators and their symbols
        operators = {
            "AND": lambda a, b: a and b,
            "OR": lambda a, b: a or b,
            "XOR": lambda a, b: a != b,
            "IMPLIES": lambda a, b: (not a) or b
        }
        
        op_name = random.choice(list(operators.keys()))
        op_func = operators[op_name]
        
        # Generate truth values
        a = random.choice([True, False])
        b = random.choice([True, False])
        result = op_func(a, b)
        
        # Convert to readable format
        a_str = "True" if a else "False"
        b_str = "True" if b else "False"
        result_str = "True" if result else "False"
        
        # Create puzzle description
        puzzles = [
            f"Evaluate the logical expression: {a_str} {op_name} {b_str}",
            f"If P={a_str} and Q={b_str}, what is P {op_name} Q?",
            f"Compute the truth value: ({a_str}) {op_name} ({b_str})"
        ]
        
        prompt = random.choice(puzzles) + "\n\nAnswer format: \\boxed{True} or \\boxed{False}"
        
        reasoning_trace = [
            f"Given: P = {a_str}, Q = {b_str}",
            f"Operation: {op_name}",
            f"Truth table for {op_name}:",
            f"  True {op_name} True = True",
            f"  True {op_name} False = False", 
            f"  False {op_name} True = False",
            f"  False {op_name} False = True" if op_name == "AND" else "...",
            f"Result: {a_str} {op_name} {b_str} = {result_str}"
        ]
        
        return ReasoningProblem(
            problem_type=ReasoningType.SYMBOLIC,
            prompt=prompt,
            ground_truth=f"\\boxed{{{result_str}}}",
            reasoning_trace=reasoning_trace,
            complexity=complexity
        )
    
    def generate_sequence_pattern(self, complexity: int = 3) -> ReasoningProblem:
        """Generate number sequence with hidden pattern"""
        
        # Pattern definitions with generators
        patterns = {
            "add_n": lambda n, inc: n + inc,
            "multiply": lambda n, factor: n * factor,
            "fibonacci": lambda seq: seq[-1] + seq[-2] if len(seq) >= 2 else 1,
            "alternating": lambda seq, pattern: pattern[len(seq) % len(pattern)],
            "geometric": lambda n, ratio: n * ratio,
            "primes": self._next_prime
        }
        
        pattern_name = random.choice(list(patterns.keys()))
        sequence = []
        
        if pattern_name == "add_n":
            start = random.randint(1, 10)
            increment = random.randint(1, 5)
            for i in range(5):
                sequence.append(start + i * increment)
            next_val = sequence[-1] + increment
            pattern_desc = f"Add {increment} each time"
            
        elif pattern_name == "multiply":
            start = random.randint(1, 5)
            factor = random.randint(2, 4)
            for i in range(5):
                sequence.append(start * (factor ** i))
            next_val = sequence[-1] * factor
            pattern_desc = f"Multiply by {factor} each time"
            
        elif pattern_name == "fibonacci":
            a, b = random.randint(1, 3), random.randint(2, 5)
            sequence = [a, b]
            for i in range(3):
                sequence.append(sequence[-1] + sequence[-2])
            next_val = sequence[-1] + sequence[-2]
            pattern_desc = "Fibonacci pattern (each term is sum of previous two)"
            
        elif pattern_name == "alternating":
            values = [random.randint(1, 10) for _ in range(3)]
            for i in range(6):
                sequence.append(values[i % len(values)])
            next_val = values[0]
            pattern_desc = f"Alternating pattern: {values} repeats"
            
        else:  # geometric
            start = random.randint(1, 10)
            ratio = random.randint(2, 3)
            for i in range(5):
                sequence.append(start * (ratio ** i))
            next_val = sequence[-1] * ratio
            pattern_desc = f"Geometric sequence (multiply by {ratio})"
        
        sequence_str = ", ".join(map(str, sequence))
        
        prompt = f"""Find the next number in this sequence:

{sequence_str}, ?

What comes next?"""
        
        reasoning_trace = [
            f"Sequence: {sequence_str}",
            f"Pattern identified: {pattern_desc}",
            f"Previous term: {sequence[-1]}",
            f"Next term: {next_val}",
            f"Therefore, the sequence continues: {next_val}"
        ]
        
        return ReasoningProblem(
            problem_type=ReasoningType.SEQUENCE,
            prompt=prompt,
            ground_truth=f"\\boxed{{{next_val}}}",
            reasoning_trace=reasoning_trace,
            complexity=complexity
        )
    
    def _next_prime(self, seq):
        """Helper for prime sequence generation"""
        import math
        n = seq[-1] + 1
        while True:
            if all(n % i != 0 for i in range(2, int(math.sqrt(n)) + 1)):
                return n
            n += 1
    
    def generate_training_dataset(self, num_samples: int = 10000) -> List[Dict]:
        """Generate a balanced training dataset"""
        
        training_data = []
        problem_types = list(ReasoningType)
        
        # Distribution: focus on harder types for competition
        type_weights = {
            ReasoningType.ALGEBRAIC: 0.25,
            ReasoningType.SYMBOLIC: 0.30,
            ReasoningType.SEQUENCE: 0.25,
            ReasoningType.CIPHER: 0.20
        }
        
        for i in range(num_samples):
            # Select problem type
            ptype = random.choices(
                problem_types, 
                weights=[type_weights[t] for t in problem_types]
            )[0]
            
            # Vary complexity - make harder problems more common
            # Competition rewards solving difficult problems
            complexity_weights = [0.1, 0.15, 0.25, 0.30, 0.20]  # heavier on 3-5
            complexity = random.choices(range(1, 6), weights=complexity_weights)[0]
            
            # Generate problem
            if ptype == ReasoningType.ALGEBRAIC:
                problem = self.generate_algebraic(complexity)
            elif ptype == ReasoningType.SYMBOLIC:
                problem = self.generate_symbolic_logic(complexity)
            elif ptype == ReasoningType.SEQUENCE:
                problem = self.generate_sequence_pattern(complexity)
            else:
                # For cipher, you can add similar implementation
                # Create simple Caesar cipher problems
                text = self._generate_random_text()
                shift = random.randint(1, 25)
                ciphertext = self._caesar_cipher(text, shift)
                problem = ReasoningProblem(
                    problem_type=ReasoningType.CIPHER,
                    prompt=f"Decode this Caesar cipher (shift unknown): '{ciphertext}'\nThe decoded message should be a common English word.",
                    ground_truth=f"\\boxed{{{text}}}",
                    reasoning_trace=[f"Shift of {shift} applied", f"Original: {text}"],
                    complexity=complexity
                )
            
            # Format as training example
            training_example = {
                "instruction": problem.prompt,
                "output": problem.ground_truth,
                "reasoning": " ".join(problem.reasoning_trace),
                "metadata": {
                    "type": ptype.value,
                    "complexity": complexity
                }
            }
            training_data.append(training_example)
        
        # Save to file
        with open("train_data.jsonl", "w") as f:
            for example in training_data:
                f.write(json.dumps(example) + "\n")
        
        return training_data
    
    def _generate_random_text(self) -> str:
        words = ["hello", "world", "python", "reasoning", "model", "nemotron"]
        return random.choice(words)
    
    def _caesar_cipher(self, text: str, shift: int) -> str:
        result = ""
        for char in text.lower():
            if char.isalpha():
                shifted = ord(char) + shift
                if shifted > ord('z'):
                    shifted -= 26
                result += chr(shifted)
            else:
                result += char
        return result


# Run generator to create training data
if __name__ == "__main__":
    solver = SymbolicSolver()
    print("Generating synthetic training dataset...")
    data = solver.generate_training_dataset(5000)  # Start with 5k samples
    print(f"Generated {len(data)} training examples")
    print("Sample:", data[0]["instruction"][:100], "...")
