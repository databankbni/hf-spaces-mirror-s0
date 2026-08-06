"""
coding_questions.py
---------------------
Static bank of hands-on coding problems for "Coding Interview" / "Coding Round"
sessions. Every problem takes JSON-serializable arguments and returns a
JSON-serializable value, so a per-language executor (see
server/services/execution/) can call it with each test case's `args` and
compare the result to `expected` — see that directory's README-style header
comments (index.js) for how JavaScript/Python/Java are dispatched.

`starter_code` is a dict keyed by language id (`"javascript"`, `"python"`,
`"java"`), pre-filled in the editor for whichever language the candidate
picks. All three must define a function/method named `function_name` with
the same effective arguments/return value — the Java executor discovers the
method via reflection and coerces each test case's JSON args to whatever
types that method actually declares, so Java starter code can (and does) use
natural, concretely-typed signatures like `int[] twoSum(int[] nums, int
target)` rather than a generic one. C is not currently offered — this
project has no C compiler available to build/verify a driver against (see
server/services/execution/index.js).

`compare_mode`:
  "exact"     — deep-equal, order matters (default if omitted)
  "unordered" — deep-equal but arrays are treated as unordered multisets,
                recursively (for problems with more than one valid ordering,
                e.g. which index comes first, or which group comes first)

`skill_tags` are topical relevance hints used to prioritize problems for
candidates whose resume mentions a related skill (see coding_question_generator.py).
They're a relevance signal, not a claim that the problem must be solved in
that language — a candidate can solve any problem in any offered language.

`test_cases` are shown to the candidate as examples. `hidden_test_cases` are
graded but never sent to the frontend.
"""

CODING_QUESTIONS = [
    {
        "id": "two-sum",
        "title": "Two Sum",
        "difficulty": "easy",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "algorithms", "data structures", "arrays"],
        "prompt": (
            "Write a function `twoSum(nums, target)` that returns the indices of the "
            "two numbers in `nums` that add up to `target`. Assume exactly one "
            "solution exists, and you may not use the same element twice."
        ),
        "function_name": "twoSum",
        "starter_code": {
            "javascript": "function twoSum(nums, target) {\n  \n}",
            "python": "def twoSum(nums, target):\n    pass",
            "java": "class Solution {\n    public int[] twoSum(int[] nums, int target) {\n        \n    }\n}",
        },
        "compare_mode": "unordered",
        "test_cases": [
            {"args": [[2, 7, 11, 15], 9], "expected": [0, 1]},
            {"args": [[3, 2, 4], 6], "expected": [1, 2]},
        ],
        "hidden_test_cases": [
            {"args": [[3, 3], 6], "expected": [0, 1]},
            {"args": [[1, 5, 3, 7], 10], "expected": [2, 3]},
        ],
        "expected_concepts": ["hash map", "time complexity", "single pass"],
    },
    {
        "id": "reverse-string",
        "title": "Reverse a String",
        "difficulty": "easy",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "strings"],
        "prompt": "Write a function `reverseString(str)` that returns `str` reversed.",
        "function_name": "reverseString",
        "starter_code": {
            "javascript": "function reverseString(str) {\n  \n}",
            "python": "def reverseString(str):\n    pass",
            "java": "class Solution {\n    public String reverseString(String str) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": ["hello"], "expected": "olleh"},
            {"args": [""], "expected": ""},
        ],
        "hidden_test_cases": [
            {"args": ["JavaScript"], "expected": "tpircSavaJ"},
            {"args": ["racecar"], "expected": "racecar"},
        ],
        "expected_concepts": ["string manipulation", "two-pointer or built-ins"],
    },
    {
        "id": "is-palindrome",
        "title": "Palindrome Check",
        "difficulty": "easy",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "strings", "algorithms"],
        "prompt": "Write a function `isPalindrome(str)` that returns true if `str` reads the same forwards and backwards.",
        "function_name": "isPalindrome",
        "starter_code": {
            "javascript": "function isPalindrome(str) {\n  \n}",
            "python": "def isPalindrome(str):\n    pass",
            "java": "class Solution {\n    public boolean isPalindrome(String str) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": ["racecar"], "expected": True},
            {"args": ["hello"], "expected": False},
        ],
        "hidden_test_cases": [
            {"args": [""], "expected": True},
            {"args": ["ab"], "expected": False},
        ],
        "expected_concepts": ["two-pointer", "string comparison"],
    },
    {
        "id": "fizzbuzz",
        "title": "FizzBuzz",
        "difficulty": "easy",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript"],
        "prompt": (
            "Write a function `fizzbuzz(n)` that returns an array of strings for 1..n where "
            "multiples of 3 are \"Fizz\", multiples of 5 are \"Buzz\", multiples of both are "
            "\"FizzBuzz\", and everything else is the number itself as a string."
        ),
        "function_name": "fizzbuzz",
        "starter_code": {
            "javascript": "function fizzbuzz(n) {\n  \n}",
            "python": "def fizzbuzz(n):\n    pass",
            "java": "class Solution {\n    public String[] fizzbuzz(int n) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": [5], "expected": ["1", "2", "Fizz", "4", "Buzz"]},
        ],
        "hidden_test_cases": [
            {"args": [3], "expected": ["1", "2", "Fizz"]},
            {"args": [15], "expected": [
                "1", "2", "Fizz", "4", "Buzz", "Fizz", "7", "8", "Fizz", "Buzz",
                "11", "Fizz", "13", "14", "FizzBuzz",
            ]},
        ],
        "expected_concepts": ["modulo operator", "conditionals"],
    },
    {
        "id": "find-max",
        "title": "Find the Maximum",
        "difficulty": "easy",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "arrays"],
        "prompt": "Write a function `findMax(nums)` that returns the largest number in the array.",
        "function_name": "findMax",
        "starter_code": {
            "javascript": "function findMax(nums) {\n  \n}",
            "python": "def findMax(nums):\n    pass",
            "java": "class Solution {\n    public int findMax(int[] nums) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": [[3, 1, 4, 1, 5, 9, 2, 6]], "expected": 9},
            {"args": [[7]], "expected": 7},
        ],
        "hidden_test_cases": [
            {"args": [[-5, -2, -10]], "expected": -2},
            {"args": [[0, 0, 0]], "expected": 0},
        ],
        "expected_concepts": ["iteration", "comparison"],
    },
    {
        "id": "count-vowels",
        "title": "Count Vowels",
        "difficulty": "easy",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "strings"],
        "prompt": "Write a function `countVowels(str)` that returns the number of vowels (a, e, i, o, u — case-insensitive) in `str`.",
        "function_name": "countVowels",
        "starter_code": {
            "javascript": "function countVowels(str) {\n  \n}",
            "python": "def countVowels(str):\n    pass",
            "java": "class Solution {\n    public int countVowels(String str) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": ["hello world"], "expected": 3},
            {"args": ["xyz"], "expected": 0},
        ],
        "hidden_test_cases": [
            {"args": ["AEIOUaeiou"], "expected": 10},
            {"args": [""], "expected": 0},
        ],
        "expected_concepts": ["string iteration", "set membership"],
    },
    {
        "id": "fibonacci",
        "title": "Fibonacci Number",
        "difficulty": "medium",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "recursion", "algorithms", "python"],
        "prompt": "Write a function `fibonacci(n)` that returns the nth Fibonacci number (fibonacci(0) = 0, fibonacci(1) = 1).",
        "function_name": "fibonacci",
        "starter_code": {
            "javascript": "function fibonacci(n) {\n  \n}",
            "python": "def fibonacci(n):\n    pass",
            "java": "class Solution {\n    public int fibonacci(int n) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": [0], "expected": 0},
            {"args": [6], "expected": 8},
        ],
        "hidden_test_cases": [
            {"args": [10], "expected": 55},
            {"args": [15], "expected": 610},
        ],
        "expected_concepts": ["recursion", "memoization", "time complexity"],
    },
    {
        "id": "valid-parentheses",
        "title": "Valid Parentheses",
        "difficulty": "medium",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "data structures", "stacks"],
        "prompt": (
            "Write a function `isValid(str)` that returns true if every bracket in `str` "
            "(made up of '()[]{}' characters) is properly opened and closed in the correct order."
        ),
        "function_name": "isValid",
        "starter_code": {
            "javascript": "function isValid(str) {\n  \n}",
            "python": "def isValid(str):\n    pass",
            "java": "class Solution {\n    public boolean isValid(String str) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": ["()[]{}"], "expected": True},
            {"args": ["(]"], "expected": False},
        ],
        "hidden_test_cases": [
            {"args": ["([)]"], "expected": False},
            {"args": [""], "expected": True},
        ],
        "expected_concepts": ["stack", "matching pairs"],
    },
    {
        "id": "group-anagrams",
        "title": "Group Anagrams",
        "difficulty": "medium",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "data structures", "hashmap", "sql"],
        "prompt": (
            "Write a function `groupAnagrams(words)` that groups words that are anagrams of "
            "each other, returning an array of arrays. Group and word order don't matter."
        ),
        "function_name": "groupAnagrams",
        "starter_code": {
            "javascript": "function groupAnagrams(words) {\n  \n}",
            "python": "def groupAnagrams(words):\n    pass",
            "java": "class Solution {\n    public List<List<String>> groupAnagrams(String[] words) {\n        \n    }\n}",
        },
        "compare_mode": "unordered",
        "test_cases": [
            {"args": [["eat", "tea", "tan", "ate", "nat", "bat"]], "expected": [["eat", "tea", "ate"], ["tan", "nat"], ["bat"]]},
        ],
        "hidden_test_cases": [
            {"args": [["abc", "bca", "cab", "xyz"]], "expected": [["abc", "bca", "cab"], ["xyz"]]},
            {"args": [[""]], "expected": [[""]]},
        ],
        "expected_concepts": ["hash map", "sorting as a key", "grouping"],
    },
    {
        "id": "merge-sorted-arrays",
        "title": "Merge Two Sorted Arrays",
        "difficulty": "medium",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "algorithms", "arrays", "sql", "mongodb", "database"],
        "prompt": "Write a function `mergeSorted(a, b)` that merges two already-sorted arrays of numbers into one sorted array.",
        "function_name": "mergeSorted",
        "starter_code": {
            "javascript": "function mergeSorted(a, b) {\n  \n}",
            "python": "def mergeSorted(a, b):\n    pass",
            "java": "class Solution {\n    public int[] mergeSorted(int[] a, int[] b) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": [[1, 3, 5], [2, 4, 6]], "expected": [1, 2, 3, 4, 5, 6]},
            {"args": [[1, 2, 3], []], "expected": [1, 2, 3]},
        ],
        "hidden_test_cases": [
            {"args": [[5, 10], [1, 2, 3]], "expected": [1, 2, 3, 5, 10]},
            {"args": [[-3, -1], [-2, 0]], "expected": [-3, -2, -1, 0]},
        ],
        "expected_concepts": ["two-pointer merge", "time complexity"],
    },
    {
        "id": "binary-search",
        "title": "Binary Search",
        "difficulty": "medium",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "algorithms"],
        "prompt": "Write a function `binarySearch(sortedNums, target)` that returns the index of `target` in the sorted array, or -1 if not found.",
        "function_name": "binarySearch",
        "starter_code": {
            "javascript": "function binarySearch(sortedNums, target) {\n  \n}",
            "python": "def binarySearch(sortedNums, target):\n    pass",
            "java": "class Solution {\n    public int binarySearch(int[] sortedNums, int target) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": [[1, 3, 5, 7, 9, 11], 7], "expected": 3},
            {"args": [[1, 3, 5, 7, 9, 11], 4], "expected": -1},
        ],
        "hidden_test_cases": [
            {"args": [[2, 4, 6, 8, 10], 2], "expected": 0},
            {"args": [[], 5], "expected": -1},
        ],
        "expected_concepts": ["binary search", "O(log n)"],
    },
    {
        "id": "flatten-array",
        "title": "Flatten a Nested Array",
        "difficulty": "medium",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "recursion", "arrays", "react"],
        "prompt": "Write a function `flattenArray(arr)` that fully flattens an arbitrarily nested array into a single flat array, preserving order.",
        "function_name": "flattenArray",
        "starter_code": {
            "javascript": "function flattenArray(arr) {\n  \n}",
            "python": "def flattenArray(arr):\n    pass",
            # Arbitrarily-nested/mixed-depth input has no single concrete Java array
            # type, so this one takes a generic Object (really a List<Object> whose
            # elements may themselves be List<Object> or Long) — check `instanceof`.
            "java": "class Solution {\n    public Object flattenArray(Object arr) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": [[1, [2, 3], [4, [5, 6]]]], "expected": [1, 2, 3, 4, 5, 6]},
            {"args": [[1, 2, 3]], "expected": [1, 2, 3]},
        ],
        "hidden_test_cases": [
            {"args": [[[1, [2]], [3, [4, [5]]]]], "expected": [1, 2, 3, 4, 5]},
            {"args": [[[[1]]]], "expected": [1]},
        ],
        "expected_concepts": ["recursion", "Array.flat semantics"],
    },
    {
        "id": "sum-nested-values",
        "title": "Sum Nested Object Values",
        "difficulty": "medium",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "recursion", "objects", "react", "json"],
        "prompt": "Write a function `sumNestedValues(obj)` that recursively sums every numeric value found anywhere in a (possibly deeply nested) object.",
        "function_name": "sumNestedValues",
        "starter_code": {
            "javascript": "function sumNestedValues(obj) {\n  \n}",
            "python": "def sumNestedValues(obj):\n    pass",
            # Arbitrarily-nested object → generic Object (really a Map<String,Object>
            # whose values may themselves be nested maps or numbers).
            "java": "class Solution {\n    public Object sumNestedValues(Object obj) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": [{"a": 1, "b": {"c": 2, "d": 3}}], "expected": 6},
            {"args": [{}], "expected": 0},
        ],
        "hidden_test_cases": [
            {"args": [{"a": {"b": {"c": {"d": 10}}}}], "expected": 10},
            {"args": [{"a": 1, "b": 2, "c": {"d": 3, "e": {"f": 4}}}], "expected": 10},
        ],
        "expected_concepts": ["recursion", "object traversal"],
    },
    {
        "id": "deep-clone",
        "title": "Deep Clone an Object",
        "difficulty": "medium",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "objects", "react", "redux"],
        "prompt": "Write a function `deepClone(value)` that returns a deep copy of a JSON-like value (objects, arrays, primitives, null).",
        "function_name": "deepClone",
        "starter_code": {
            "javascript": "function deepClone(value) {\n  \n}",
            "python": "def deepClone(value):\n    pass",
            # Could be anything (object, array, primitive, or null) → generic Object.
            "java": "class Solution {\n    public Object deepClone(Object value) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": [{"a": 1, "b": {"c": 2}}], "expected": {"a": 1, "b": {"c": 2}}},
            {"args": [[1, [2, 3]]], "expected": [1, [2, 3]]},
        ],
        "hidden_test_cases": [
            {"args": [{"x": [1, 2, {"y": 3}]}], "expected": {"x": [1, 2, {"y": 3}]}},
            {"args": [None], "expected": None},
        ],
        "expected_concepts": ["recursion", "reference vs. value"],
    },
    {
        "id": "rotate-array",
        "title": "Rotate an Array",
        "difficulty": "medium",
        "category": "Data Structures & Algorithms",
        "skill_tags": ["javascript", "arrays", "algorithms"],
        "prompt": "Write a function `rotateArray(nums, k)` that rotates the array to the right by `k` positions.",
        "function_name": "rotateArray",
        "starter_code": {
            "javascript": "function rotateArray(nums, k) {\n  \n}",
            "python": "def rotateArray(nums, k):\n    pass",
            "java": "class Solution {\n    public int[] rotateArray(int[] nums, int k) {\n        \n    }\n}",
        },
        "test_cases": [
            {"args": [[1, 2, 3, 4, 5], 2], "expected": [4, 5, 1, 2, 3]},
            {"args": [[1], 5], "expected": [1]},
        ],
        "hidden_test_cases": [
            {"args": [[1, 2, 3, 4], 0], "expected": [1, 2, 3, 4]},
            {"args": [[1, 2, 3, 4, 5, 6], 3], "expected": [4, 5, 6, 1, 2, 3]},
        ],
        "expected_concepts": ["array manipulation", "modulo for wraparound"],
    },
]
