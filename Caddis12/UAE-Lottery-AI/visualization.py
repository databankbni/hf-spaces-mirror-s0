import matplotlib.pyplot as plt

from data import load_data
from analysis import number_frequency


def create_frequency_chart():
    """
    Create a frequency chart and return the figure.
    """

    data = load_data()

    frequency = number_frequency(data)

    numbers = list(frequency.keys())
    counts = list(frequency.values())

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.bar(numbers, counts)

    ax.set_title("Lottery Number Frequency")
    ax.set_xlabel("Lottery Numbers")
    ax.set_ylabel("Frequency")

    ax.set_xticks(range(1, 32))

    ax.grid(axis="y", linestyle="--", alpha=0.4)

    return fig

# Testing code
if __name__ == "__main__":

    create_frequency_chart()
