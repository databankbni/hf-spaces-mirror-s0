import pandas as pd

from data import load_data


def create_features(dataframe):
    """
    Create additional features from each lottery draw.
    """

    features = pd.DataFrame()

    features["Sum"] = dataframe.sum(axis=1)

    features["Odd_Count"] = dataframe.apply(
        lambda row: sum(number % 2 != 0 for number in row),
        axis=1
    )

    features["Even_Count"] = dataframe.apply(
        lambda row: sum(number % 2 == 0 for number in row),
        axis=1
    )

    features["Lowest"] = dataframe.min(axis=1)

    features["Highest"] = dataframe.max(axis=1)

    features["Range"] = features["Highest"] - features["Lowest"]

    return features


if __name__ == "__main__":

    data = load_data()

    print("Original Lottery Draws:")
    print(data.head())

    print("\nEngineered Features:")
    features = create_features(data)
    print(features.head())