from data import load_data
from analysis import (
    dataset_summary,
    number_frequency,
    hot_numbers,
    cold_numbers,
    common_pairs,
    common_triplets
)

def generate_report():
    """
    Generate a complete lottery analysis report.
    """

    data = load_data()

    summary = dataset_summary(data)

    frequency = number_frequency(data)

    hot = hot_numbers(frequency)

    cold = cold_numbers(frequency)

    pairs = common_pairs(data)

    triplets = common_triplets(data)

    report = ""

    report += "=" * 50 + "\n"
    report += "LOTTERY ANALYSIS REPORT\n"
    report += "=" * 50 + "\n\n"

    report += "DATASET SUMMARY\n"
    report += "-" * 50 + "\n"

    for key, value in summary.items():
        report += f"{key}: {value}\n"

    report += "\n"

    report += "TOP HOT NUMBERS\n"
    report += "-" * 50 + "\n"

    for number, count in hot:
        report += f"{number:>2} : {count}\n"

    report += "\n"

    report += "TOP COLD NUMBERS\n"
    report += "-" * 50 + "\n"

    for number, count in cold:
        report += f"{number:>2} : {count}\n"

    report += "\n"

    report += "MOST COMMON PAIRS\n"
    report += "-" * 50 + "\n"

    for pair, count in pairs:
        report += f"{pair} : {count}\n"

    report += "\n"

    report += "MOST COMMON TRIPLETS\n"
    report += "-" * 50 + "\n"

    for triplet, count in triplets:
        report += f"{triplet} : {count}\n"

    return report

if __name__ == "__main__":

    print(generate_report())
