from data import load_data
from sklearn.ensemble import RandomForestRegressor
import numpy as np

# train model
def train_model():
    """
    Train a simple Random Forest model using historical lottery draws.
    """

    dataframe = load_data()

    X = np.arange(len(dataframe)).reshape(-1, 1)
    y = dataframe.values

    model = RandomForestRegressor(
        n_estimators=100,
        random_state=42
    )

    model.fit(X, y)

    return model

# predict next draw
def predict_next_draw():

    model = train_model()

    next_draw = np.array([[len(load_data())]])

    prediction = model.predict(next_draw)[0]

    prediction = [round(number) for number in prediction]

    prediction = [
        max(1, min(31, number))
        for number in prediction
    ]

    prediction = sorted(list(set(prediction)))

    return prediction

if __name__ == "__main__":

    prediction = predict_next_draw()

    print("Machine Learning Prediction")

    print(prediction)