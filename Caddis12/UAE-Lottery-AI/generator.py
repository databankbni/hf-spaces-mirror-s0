import random

from ml_predictor import predict_next_draw
from predictor import predict_next_numbers
from data import load_data
from analysis import (
    number_frequency,
    hot_numbers,
    cold_numbers
)

# Is balance odd or even
def is_balanced_odd_even(numbers):
    """
    Check whether the draw has a balanced mix of odd and even numbers.
    """

    odd = sum(number % 2 != 0 for number in numbers)
    even = sum(number % 2 == 0 for number in numbers)

    return odd == 3 and even == 3

# Has good range
def has_good_range(numbers):
    """
    Check whether the numbers are well spread out.
    """

    spread = max(numbers) - min(numbers)

    return spread >= 20

# Already exists
def already_exists(dataframe, numbers):
    """
    Check whether the lottery draw already exists in the dataset.
    """

    numbers = sorted(numbers)

    return ((dataframe == numbers).all(axis=1)).any()

# Calculate score
def calculate_score(numbers, frequency):
    """
    Calculate a score for a lottery ticket.
    Higher scores are considered better according to our rules.
    """

    score = 0

    # Reward hot numbers
    for number in numbers:
        score += frequency[number]

    # Reward balanced odd/even
    if is_balanced_odd_even(numbers):
        score += 20

    # Reward good spread
    if has_good_range(numbers):
        score += 20

    # Reward good distribution
    if has_good_distribution(numbers):
        score += 25    

    return score

# Has too many consecutives
def has_too_many_consecutive(numbers):
    """
    Return True if there are 3 or more consecutive numbers.
    """

    consecutive = 1

    for i in range(1, len(numbers)):

        if numbers[i] == numbers[i - 1] + 1:
            consecutive += 1

            if consecutive >= 3:
                return True

        else:
            consecutive = 1

    return False

# Has good distribution
def has_good_distribution(numbers):
    """
    Check whether the numbers are spread across
    the three sections of the lottery.
    """

    low = 0
    middle = 0
    high = 0

    for number in numbers:

        if 1 <= number <= 10:
            low += 1

        elif 11 <= number <= 20:
            middle += 1

        else:
            high += 1

    return low >= 1 and middle >= 1 and high >= 1

# Generate numbers
def generate_numbers(iterations=1000):
    """
    Generate the best lottery ticket from many candidates.
    """

    data = load_data()

    frequency = number_frequency(data)

    # Get the AI prediction
    pool = predict_next_numbers()

    ml_numbers = predict_next_draw()

    for number in ml_numbers:

        if number not in pool:

          pool.append(number)

    # Add random numbers so the search has more options
    while len(pool) < 20:

      number = random.randint(1, 31)

      if number not in pool:
         pool.append(number)

    best_ticket = None
    best_score = -1     

    # Try 100 candidate tickets
    for _ in range(iterations):

        candidate = random.sample(pool, 6)
        candidate.sort()

        if not is_balanced_odd_even(candidate):
            continue

        if not has_good_range(candidate):
            continue

        if already_exists(data, candidate):
            continue

        score = calculate_score(candidate, frequency)

        if score > best_score:
            best_score = score
            best_ticket = candidate

    return {
     "numbers": best_ticket,
     "score": best_score,
     "odd": sum(n % 2 != 0 for n in best_ticket),
     "even": sum(n % 2 == 0 for n in best_ticket),
     "sum": sum(best_ticket),
     "range": max(best_ticket) - min(best_ticket),
     "lowest": min(best_ticket),
     "highest": max(best_ticket),
     "iterations": iterations,
    }

# Testing code
if __name__ == "__main__":

    numbers, score = generate_numbers(iterations=1000)

    print("=================================")
    print(" SMART LOTTERY GENERATOR")
    print("=================================")

    print("\nSuggested Numbers:")

    for number in numbers:
        print(number)

    print(f"\nScore: {score}")
    print("Tickets Evaluated: 1000")
    print(f"Odd Numbers: {sum(n % 2 != 0 for n in numbers)}")
    print(f"Even Numbers: {sum(n % 2 == 0 for n in numbers)}")
    print(f"Lowest Number: {min(numbers)}")
    print(f"Highest Number: {max(numbers)}")
    print(f"Range: {max(numbers) - min(numbers)}")
    print(f"Sum: {sum(numbers)}")

    for number in numbers:
        print(number)

    print(f"\nScore: {score}")