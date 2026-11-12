"""Test the classifier + router end-to-end without an LLM call."""

from app.classifier import classify
from app.router import dry_run


TESTS = [
    # general / factual / low complexity
    "what is your name",
    "what is java",
    "what is the capital of France",
    "what is a palindrome",
    "when did World War 2 end",

    # general / medium
    "tell me about yourself",
    "why do you want to work here",
    "what are your strengths and weaknesses",

    # reasoning
    "explain the difference between process and thread",
    "compare Kafka and RabbitMQ",
    "why is the sky blue",
    "analyze the tradeoffs of microservices vs monolith",

    # reasoning / high
    "design a distributed cache with 10 nodes and explain the tradeoffs",
    "evaluate the impact of shifting our event pipeline to exactly-once semantics",

    # code / low
    "write a prime number program",
    "reverse a string",
    "write a function to check if a number is prime",

    # code / medium
    "implement a function to reverse a linked list",
    "write code to find two numbers that sum to a target",
    "create a python function to check if a string is a palindrome",

    # code / high
    "implement a concurrent LRU cache with time complexity O(1) for get and put",
    "write a dynamic programming solution for the knapsack problem with memoization and analyze time complexity",
]


def main():
    print(f"{'Question':<65}  {'Intent':<10} {'Cx':<7} {'Tier':<5} {'Model':<40} {'$/M':>8}")
    print("-" * 145)
    for q in TESTS:
        r = dry_run(q)
        c = r["classification"]
        m = r["selected_model"]

        model_label = f"{m['provider']}/{m['model_id']}" if m else "NONE"
        cost = m["cost"] if m else 0.0

        # truncate long labels for column alignment
        q_short = (q[:62] + "...") if len(q) > 65 else q
        model_short = (model_label[:38] + "..") if len(model_label) > 40 else model_label

        print(
            f"{q_short:<65}  "
            f"{c['intent']:<10} "
            f"{c['complexity']:<7} "
            f"{c['required_tier']:<5} "
            f"{model_short:<40} "
            f"${cost:>6.3f}"
        )


if __name__ == "__main__":
    main()
    