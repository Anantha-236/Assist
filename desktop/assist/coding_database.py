"""Curated coding interview problems with tested reference solutions."""

CODING_PROBLEMS = [
    {
        "id": "prime_check",
        "category": "math",
        "difficulty": "easy",
        "patterns": ["check if a number is prime", "check prime", "is prime",
                     "prime check", "check prime number"],
        "explanation": "Trial division only needs to test factors through the square root.",
        "code": {
            "python": (
                "def is_prime(n: int) -> bool:\n"
                "    if n < 2:\n        return False\n"
                "    if n == 2:\n        return True\n"
                "    if n % 2 == 0:\n        return False\n"
                "    i = 3\n"
                "    while i * i <= n:\n"
                "        if n % i == 0:\n            return False\n"
                "        i += 2\n"
                "    return True"
            ),
            "javascript": (
                "function isPrime(n) {\n"
                "  if (n < 2) return false;\n"
                "  if (n % 2 === 0) return n === 2;\n"
                "  for (let i = 3; i * i <= n; i += 2)\n"
                "    if (n % i === 0) return false;\n"
                "  return true;\n}"
            ),
        },
        "complexity": "O(sqrt(n)) time, O(1) space",
    },
    {
        "id": "prime_first_n",
        "category": "math",
        "difficulty": "easy",
        "patterns": ["first 10 prime", "first n prime", "first n primes",
                     "print prime numbers", "generate prime", "list prime"],
        "explanation": "Test consecutive candidates until the requested number of primes is collected.",
        "code": {
            "python": (
                "def first_n_primes(n: int) -> list[int]:\n"
                "    primes = []\n"
                "    candidate = 2\n"
                "    while len(primes) < n:\n"
                "        if is_prime(candidate):\n"
                "            primes.append(candidate)\n"
                "        candidate += 1\n"
                "    return primes"
            ),
        },
        "complexity": "O(N * sqrt(p)) time, O(N) space",
    },
    {
        "id": "fibonacci",
        "category": "math",
        "difficulty": "easy",
        "patterns": ["fibonacci", "fibonacci series", "fibonacci number",
                     "fibonacci sequence", "nth fibonacci"],
        "explanation": "Use an iterative pair of values instead of exponential recursion.",
        "code": {
            "python": (
                "def fib(n: int) -> int:\n"
                "    a, b = 0, 1\n"
                "    for _ in range(n):\n"
                "        a, b = b, a + b\n"
                "    return a"
            ),
            "javascript": (
                "function fib(n) {\n"
                "  let a = 0, b = 1;\n"
                "  for (let i = 0; i < n; i++) [a, b] = [b, a + b];\n"
                "  return a;\n}"
            ),
        },
        "complexity": "O(n) time, O(1) space",
    },
    {
        "id": "factorial",
        "category": "math",
        "difficulty": "easy",
        "patterns": ["factorial", "factorial of", "n factorial"],
        "explanation": "An iterative product avoids recursion depth limits.",
        "code": {
            "python": (
                "def factorial(n: int) -> int:\n"
                "    result = 1\n"
                "    for value in range(2, n + 1):\n"
                "        result *= value\n"
                "    return result"
            ),
        },
        "complexity": "O(n) time, O(1) space",
    },
    {
        "id": "gcd",
        "category": "math",
        "difficulty": "easy",
        "patterns": ["gcd", "greatest common divisor", "greatest common factor",
                     "hcf", "highest common factor"],
        "explanation": "The Euclidean algorithm repeatedly replaces (a, b) with (b, a mod b).",
        "code": {
            "python": (
                "def gcd(a: int, b: int) -> int:\n"
                "    while b:\n"
                "        a, b = b, a % b\n"
                "    return abs(a)"
            ),
        },
        "complexity": "O(log(min(a, b))) time, O(1) space",
    },
    {
        "id": "reverse_string",
        "category": "string",
        "difficulty": "easy",
        "patterns": ["reverse a string", "reverse string", "string reversal",
                     "reverse the string"],
        "explanation": "Reverse the sequence without changing the original input.",
        "code": {
            "python": "def reverse_string(s: str) -> str:\n    return s[::-1]",
            "javascript": "function reverseString(s) {\n  return [...s].reverse().join('');\n}",
            "java": "static String reverseString(String s) {\n    return new StringBuilder(s).reverse().toString();\n}",
        },
        "complexity": "O(n) time, O(n) space",
    },
    {
        "id": "reverse_number",
        "category": "math",
        "difficulty": "easy",
        "patterns": ["reverse a number", "reverse number", "reverse digits",
                     "reverse integer"],
        "explanation": "Extract digits from the end and build the reversed number.",
        "code": {
            "python": (
                "def reverse_number(n: int) -> int:\n"
                "    sign = -1 if n < 0 else 1\n"
                "    n = abs(n)\n"
                "    result = 0\n"
                "    while n:\n"
                "        result = result * 10 + n % 10\n"
                "        n //= 10\n"
                "    return sign * result"
            ),
        },
        "complexity": "O(log10(n)) time, O(1) space",
    },
    {
        "id": "palindrome_string",
        "category": "string",
        "difficulty": "easy",
        "patterns": ["palindrome string", "check palindrome", "is palindrome",
                     "check if a string is palindrome"],
        "explanation": "Compare characters from both ends with two pointers.",
        "code": {
            "python": (
                "def is_palindrome(s: str) -> bool:\n"
                "    s = s.lower()\n"
                "    return s == s[::-1]"
            ),
        },
        "complexity": "O(n) time, O(n) space",
    },
    {
        "id": "anagram_check",
        "category": "string",
        "difficulty": "easy",
        "patterns": ["anagram", "check anagram", "are two strings anagrams"],
        "explanation": "Compare character frequency counts in both strings.",
        "code": {
            "python": (
                "from collections import Counter\n\n"
                "def is_anagram(a: str, b: str) -> bool:\n"
                "    return Counter(a.lower()) == Counter(b.lower())"
            ),
        },
        "complexity": "O(n) time, O(n) space",
    },
    {
        "id": "count_vowels",
        "category": "string",
        "difficulty": "easy",
        "patterns": ["count vowels", "number of vowels", "vowel count"],
        "explanation": "Count characters that belong to the vowel set.",
        "code": {
            "python": (
                "def count_vowels(s: str) -> int:\n"
                "    return sum(c in 'aeiou' for c in s.lower())"
            ),
        },
        "complexity": "O(n) time, O(1) space",
    },
    {
        "id": "reverse_words",
        "category": "string",
        "difficulty": "medium",
        "patterns": ["reverse words in a string", "reverse word order",
                     "reverse words"],
        "explanation": "Split on whitespace, reverse the words, and join them.",
        "code": {
            "python": "def reverse_words(s: str) -> str:\n    return ' '.join(s.split()[::-1])",
        },
        "complexity": "O(n) time, O(n) space",
    },
    {
        "id": "two_sum",
        "category": "array",
        "difficulty": "easy",
        "patterns": ["two sum", "find two numbers", "pair sum",
                     "two numbers that add", "find pair with sum"],
        "explanation": "Store previously seen values and look up each value's complement.",
        "code": {
            "python": (
                "def two_sum(nums: list[int], target: int) -> list[int]:\n"
                "    seen = {}\n"
                "    for i, value in enumerate(nums):\n"
                "        if target - value in seen:\n"
                "            return [seen[target - value], i]\n"
                "        seen[value] = i\n"
                "    return []"
            ),
        },
        "complexity": "O(n) time, O(n) space",
    },
    {
        "id": "max_subarray",
        "category": "array",
        "difficulty": "medium",
        "patterns": ["maximum subarray", "max subarray sum", "kadane",
                     "maximum contiguous sum"],
        "explanation": "Kadane's algorithm tracks the best subarray ending at each position.",
        "code": {
            "python": (
                "def max_subarray(nums: list[int]) -> int:\n"
                "    best = current = nums[0]\n"
                "    for value in nums[1:]:\n"
                "        current = max(value, current + value)\n"
                "        best = max(best, current)\n"
                "    return best"
            ),
        },
        "complexity": "O(n) time, O(1) space",
    },
    {
        "id": "find_duplicates",
        "category": "array",
        "difficulty": "easy",
        "patterns": ["find duplicates", "duplicate in array",
                     "duplicate elements", "repeated element"],
        "explanation": "A set tracks values already encountered.",
        "code": {
            "python": (
                "def find_duplicates(nums: list[int]) -> list[int]:\n"
                "    seen, duplicates = set(), set()\n"
                "    for value in nums:\n"
                "        if value in seen:\n"
                "            duplicates.add(value)\n"
                "        seen.add(value)\n"
                "    return list(duplicates)"
            ),
        },
        "complexity": "O(n) time, O(n) space",
    },
    {
        "id": "missing_number",
        "category": "array",
        "difficulty": "easy",
        "patterns": ["missing number", "find missing number",
                     "missing in array"],
        "explanation": "Subtract the actual sum from the expected 1..n sum.",
        "code": {
            "python": (
                "def missing_number(nums: list[int], n: int) -> int:\n"
                "    return n * (n + 1) // 2 - sum(nums)"
            ),
        },
        "complexity": "O(n) time, O(1) space",
    },
    {
        "id": "binary_search",
        "category": "search",
        "difficulty": "easy",
        "patterns": ["binary search", "search in sorted array",
                     "find element in sorted array"],
        "explanation": "Halve the search range after each comparison; the input must be sorted.",
        "code": {
            "python": (
                "def binary_search(nums: list[int], target: int) -> int:\n"
                "    lo, hi = 0, len(nums) - 1\n"
                "    while lo <= hi:\n"
                "        mid = (lo + hi) // 2\n"
                "        if nums[mid] == target:\n"
                "            return mid\n"
                "        if nums[mid] < target:\n"
                "            lo = mid + 1\n"
                "        else:\n"
                "            hi = mid - 1\n"
                "    return -1"
            ),
        },
        "complexity": "O(log n) time, O(1) space",
    },
    {
        "id": "bubble_sort",
        "category": "sort",
        "difficulty": "easy",
        "patterns": ["bubble sort", "bubble sort algorithm", "implement bubble sort"],
        "explanation": "Repeatedly swap adjacent out-of-order values; this is simple but quadratic.",
        "code": {
            "python": (
                "def bubble_sort(nums: list[int]) -> list[int]:\n"
                "    nums = nums[:]\n"
                "    for end in range(len(nums) - 1, 0, -1):\n"
                "        swapped = False\n"
                "        for i in range(end):\n"
                "            if nums[i] > nums[i + 1]:\n"
                "                nums[i], nums[i + 1] = nums[i + 1], nums[i]\n"
                "                swapped = True\n"
                "        if not swapped:\n"
                "            break\n"
                "    return nums"
            ),
            "javascript": (
                "function bubbleSort(nums) {\n"
                "  nums = [...nums];\n"
                "  for (let end = nums.length - 1; end > 0; end--) {\n"
                "    let swapped = false;\n"
                "    for (let i = 0; i < end; i++) {\n"
                "      if (nums[i] > nums[i + 1]) {\n"
                "        [nums[i], nums[i + 1]] = [nums[i + 1], nums[i]];\n"
                "        swapped = true;\n"
                "      }\n"
                "    }\n"
                "    if (!swapped) break;\n"
                "  }\n"
                "  return nums;\n}"
            ),
        },
        "complexity": "O(n^2) time, O(1) extra space",
    },
    {
        "id": "merge_sort",
        "category": "sort",
        "difficulty": "medium",
        "patterns": ["merge sort", "merge sort algorithm", "implement merge sort"],
        "explanation": "Divide the array, sort both halves, and merge the sorted results.",
        "code": {
            "python": (
                "def merge_sort(nums: list[int]) -> list[int]:\n"
                "    if len(nums) <= 1:\n"
                "        return nums[:]\n"
                "    mid = len(nums) // 2\n"
                "    left, right = merge_sort(nums[:mid]), merge_sort(nums[mid:])\n"
                "    out, i, j = [], 0, 0\n"
                "    while i < len(left) and j < len(right):\n"
                "        if left[i] <= right[j]:\n"
                "            out.append(left[i]); i += 1\n"
                "        else:\n"
                "            out.append(right[j]); j += 1\n"
                "    return out + left[i:] + right[j:]"
            ),
        },
        "complexity": "O(n log n) time, O(n) space",
    },
    {
        "id": "quick_sort",
        "category": "sort",
        "difficulty": "medium",
        "patterns": ["quick sort", "quicksort", "quick sort algorithm",
                     "implement quick sort"],
        "explanation": "Partition around a pivot, then recursively sort both sides.",
        "code": {
            "python": (
                "def quick_sort(nums: list[int]) -> list[int]:\n"
                "    if len(nums) <= 1:\n"
                "        return nums[:]\n"
                "    pivot = nums[len(nums) // 2]\n"
                "    left = [x for x in nums if x < pivot]\n"
                "    middle = [x for x in nums if x == pivot]\n"
                "    right = [x for x in nums if x > pivot]\n"
                "    return quick_sort(left) + middle + quick_sort(right)"
            ),
        },
        "complexity": "O(n log n) average time, O(n^2) worst case",
    },
    {
        "id": "insertion_sort",
        "category": "sort",
        "difficulty": "easy",
        "patterns": ["insertion sort", "insertion sort algorithm",
                     "implement insertion sort"],
        "explanation": "Insert each next value into the sorted prefix.",
        "code": {
            "python": (
                "def insertion_sort(nums: list[int]) -> list[int]:\n"
                "    nums = nums[:]\n"
                "    for i in range(1, len(nums)):\n"
                "        value, j = nums[i], i - 1\n"
                "        while j >= 0 and nums[j] > value:\n"
                "            nums[j + 1] = nums[j]\n"
                "            j -= 1\n"
                "        nums[j + 1] = value\n"
                "    return nums"
            ),
        },
        "complexity": "O(n^2) time, O(1) extra space",
    },
    {
        "id": "fizzbuzz",
        "category": "misc",
        "difficulty": "easy",
        "patterns": ["fizzbuzz", "fizz buzz", "fizz-buzz", "implement fizzbuzz"],
        "explanation": "Check divisibility by 15 before checking 3 or 5.",
        "code": {
            "python": (
                "def fizzbuzz(n: int) -> list[str]:\n"
                "    result = []\n"
                "    for i in range(1, n + 1):\n"
                "        if i % 15 == 0:\n"
                "            result.append('FizzBuzz')\n"
                "        elif i % 3 == 0:\n"
                "            result.append('Fizz')\n"
                "        elif i % 5 == 0:\n"
                "            result.append('Buzz')\n"
                "        else:\n"
                "            result.append(str(i))\n"
                "    return result"
            ),
        },
        "complexity": "O(n) time, O(n) space",
    },
]


def get_problem(problem_id: str) -> dict | None:
    return next((problem for problem in CODING_PROBLEMS
                 if problem["id"] == problem_id), None)


def pick_code(problem: dict, user_languages: list[str]) -> tuple[str, str]:
    """Choose a preferred implementation, falling back to Python."""
    code = problem.get("code", {})
    for language in user_languages:
        key = language.lower().strip()
        if key in code:
            return key, code[key]
    if "python" in code:
        return "python", code["python"]
    if not code:
        return "", ""
    language = next(iter(code))
    return language, code[language]
