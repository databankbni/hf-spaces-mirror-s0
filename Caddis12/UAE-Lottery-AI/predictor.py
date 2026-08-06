from data import load_data
from analysis import number_frequency, hot_numbers, cold_numbers
import random


def predict_next_numbers():
    """
    Build a smart candidate pool using historical analysis.
    """

    dataframe = load_data()

    frequency = number_frequency(dataframe)

    pool = []

    for number, count in hot_numbers(frequency, top=10):
        pool.append(number)

    for number, count in cold_numbers(frequency, top=5):
        pool.append(number)

    # Add random numbers until the pool contains 20 unique numbers
    while len(pool) < 20:

        number = random.randint(1, 31)

        if number not in pool:
            pool.append(number)

    return sorted(pool)

if __name__ == "__main__":

    prediction = predict_next_numbers()

    print("Predicted Numbers")

    print(prediction)