from itertools import combinations
import pandas as pd
from data import load_data

# Dataset summary
def dataset_summary(dataframe):
    """
    Return basic information about the dataset.
    """

    summary = {
        "Total Draws": len(dataframe),
        "Lowest Number": int(dataframe.min().min()),
        "Highest Number": int(dataframe.max().max())
    }

    return summary


# Number Frequency
def number_frequency(dataframe):
    """
    Count how many times each lottery number appears.
    """

    frequency = {}

    # Create keys from 1 to 31
    for number in range(1, 32):
        frequency[number] = 0

    # Count every occurrence
    for column in dataframe.columns:

        counts = dataframe[column].value_counts()

        for number, total in counts.items():
            frequency[number] += total

    return frequency

# Find the Hot Numbers
def hot_numbers(frequency, top=10):

    sorted_numbers = sorted(
        frequency.items(),
        key=lambda item: item[1],
        reverse=True
    )

    return sorted_numbers[:top]

# cold numbers
def cold_numbers(frequency, top=10):

    sorted_numbers = sorted(
        frequency.items(),
        key=lambda item: item[1]
    )

    return sorted_numbers[:top]

# Common pairs
def common_pairs(dataframe, top=10):
    """
    Find the most common pairs of numbers.
    """

    pair_counts = {}

    for _, row in dataframe.iterrows():

        numbers = sorted(row.tolist())

        for pair in combinations(numbers, 2):

            if pair in pair_counts:
                pair_counts[pair] += 1
            else:
                pair_counts[pair] = 1

    sorted_pairs = sorted(
        pair_counts.items(),
        key=lambda item: item[1],
        reverse=True
    )

    return sorted_pairs[:top]

# Common triplets
def common_triplets(dataframe, top=10):
    """
    Find the most common triplets of numbers.
    """

    triplet_counts = {}

    for _, row in dataframe.iterrows():

        numbers = sorted(row.tolist())

        for triplet in combinations(numbers, 3):

            if triplet in triplet_counts:
                triplet_counts[triplet] += 1
            else:
                triplet_counts[triplet] = 1

    sorted_triplets = sorted(
        triplet_counts.items(),
        key=lambda item: item[1],
        reverse=True
    )

    return sorted_triplets[:top]


# Testing code
if __name__ == "__main__":

    data = load_data()

    triplets = common_triplets(data)

    print("Top 10 Most Common Triplets")
    print("---------------------------")

    for triplet, count in triplets:
        print(f"{triplet} : {count}")