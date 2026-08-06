import pandas as pd

FILE_NAME = 'lottery_data.xlsx'

def load_data():
    """
    Load the lottery data from the Excel file.
    """

    dataframe = pd.read_excel(FILE_NAME, header=None)
    dataframe.columns = ["N1", "N2", "N3", "N4","N5", "N6"]
    return dataframe


# vaildate the Dataset
def validate_data(dataframe):
    """
    Check if the lottery data is valid.
    """

    for index, row in dataframe.iterrows():

        numbers = row.tolist()

        if len(set(numbers)) != 6:
            print(f"Duplicate numbers found in row {index + 1}")
            return False

        for number in numbers:

            if number < 1 or number > 31:
                print(f"Invalid number {number} found in row {index + 1}")
                return False

    print("Dataset validation passed.")

    return True  

# Adding a new winning draw
def add_draw(dataframe, numbers):
    """
    Add a new lottery draw to the dataset.
    """

    # Validate the new draw first
    if not validate_new_draw(numbers):
        print("Draw was not saved.")
        return dataframe

    # Check if the draw already exists
    if ((dataframe == numbers).all(axis=1)).any():
        return dataframe, "❌ This draw already exists."

    # Create a new row
    new_row = pd.DataFrame([numbers], columns=dataframe.columns)

    # Append the new row
    dataframe = pd.concat([dataframe, new_row], ignore_index=True)

    # Save to Excel
    dataframe.to_excel(FILE_NAME, index=False, header=False)

    return dataframe, "✅ New draw saved successfully."

# Validate the users input
def validate_new_draw(numbers):
    """
    Validate a new lottery draw entered by the user.
    """

    if len(numbers) != 6:
        print("A lottery draw must contain exactly 6 numbers.")
        return False

    if len(set(numbers)) != 6:
        print("Duplicate numbers are not allowed.")
        return False

    for number in numbers:

        if not isinstance(number, int):
            print(f"{number} is not an integer.")
            return False

        if number < 1 or number > 31:
            print(f"{number} is outside the valid range (1-31).")
            return False

    return True

if __name__ == '__main__':

    data = load_data()

    new_numbers = input("Enter the new draw (comma-separated): ")

    new_numbers = new_numbers.split(",")

    new_numbers = [int(number.strip()) for number in new_numbers]

    data = add_draw(data, new_numbers)   

    
