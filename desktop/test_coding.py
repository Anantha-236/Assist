"""Test coding question matching — no string escaping issues."""

from assist.coding_matcher import build_coding_answer, match_coding_question


TESTS = [
    ("write a program to print first 10 prime numbers", "prime_first_n"),
    ("check if a number is prime", "prime_check"),
    ("write code to reverse a string", "reverse_string"),
    ("implement merge sort", "merge_sort"),
    ("how do you do binary search", "binary_search"),
    ("find two numbers that add up to a target", "two_sum"),
    ("what is fizzbuzz", "fizzbuzz"),
    ("write a quick sort algorithm", "quick_sort"),
    ("tell me about yourself", None),
    ("write a function to check if a string is a palindrome", "palindrome_string"),
    ("how do you implement bubble sort", "bubble_sort"),
    ("write a code to reverse a number", "reverse_number"),
]

print(f"{'Result':<12} {'Expected':<22} {'Question':<60}")
print("-" * 100)

correct = 0
for text, expected in TESTS:
    match = match_coding_question(text)
    actual = match["id"] if match else None
    ok = actual == expected
    correct += int(ok)
    mark = "OK" if ok else "FAIL"
    print(f"{mark:<12} {(expected or 'NO-MATCH'):<22} {text[:58]}")

print()
print(f"{correct}/{len(TESTS)} passed")

print()
print("=" * 80)
print("Sample answer for: 'write a program to print first 10 prime numbers'")
print("=" * 80)
match = match_coding_question(TESTS[0][0])
if match:
    print(build_coding_answer(match, ["Python"]))

if correct != len(TESTS):
    raise SystemExit(1)
