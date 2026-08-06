
import pandas as pd
import streamlit as st
import requests

st.title("SuperKart Revenue Sales Forecasting App") #Complete the code to define the title of the app.
st.write("This app predicts Product Store Sales Total")

# Section for online prediction
st.subheader("Online Prediction")

# Input fields for product and store data
Product_Weight = st.number_input("Product Weight", min_value=0.0, value=12.66)
Product_Sugar_Content = st.selectbox("Product Sugar Content", ["No Sugar", "Low Sugar", "Regular"])
Product_Allocated_Area = st.number_input("Ratio of the Allocated Display Area", min_value=0.00, max_value=1.00, value= 0.056) #UI element for Product_Allocated_Area
Product_MRP = st.number_input("Maximum Retail Sales Price", min_value=30.00, max_value=300.00, value= 146.74) #UI element for Product_MRP
Store_Size = st.selectbox("Store Size", ["Small","Medium","Large"]) #UI element for Store_Size
Store_Location_City_Type = st.selectbox("Type of the City where Store is Located", ["Tier 1","Tier 2","Tier 3"]) #UI element for Store_Location_City_Type
Store_Type = st.selectbox("Type of Store", ["Departamental Store","Supermarket Type 1","Supermarket Type 2","Food Mart"]) #UI element for Store_Type
Product_Id_char = st.selectbox("Product Category: FD->Food / DR->Drinks / NC->Hygiene, Personal and Household & Others ", ["FD","DR","NC"]) #UI element for Product_Id_char
Store_Age_Years = st.number_input("Store Age (in years)", min_value=17, max_value=39, value= 24, step=1) #UI element for Store_Age_Years
Product_Type_Category = st.selectbox("Product Type Category:", ["Perishables", "Non Perishables"])

product_data = {
    "Product_Weight": Product_Weight,
    "Product_Sugar_Content": Product_Sugar_Content,
    "Product_Allocated_Area": Product_Allocated_Area,
    "Product_MRP": Product_MRP,
    "Store_Size": Store_Size,
    "Store_Location_City_Type": Store_Location_City_Type,
    "Store_Type": Store_Type,
    "Product_Id_char": Product_Id_char,
    "Store_Age_Years": Store_Age_Years,
    "Product_Type_Category": Product_Type_Category
}


if st.button("Predict", type='primary'):
    response = requests.post("https://cemoreno-superkartforecastingbackend.hf.space/v1/predict", json=product_data)    # Corrected to call backend function
    if response.status_code == 200:
        result = response.json()
        predicted_sales = result["Sales"]
        st.write(f"Predicted Product Store Sales Total: $ {predicted_sales:.2f}")
    else:
        st.error("Error in API request")

# Section for batch prediction
st.subheader("Batch Prediction")

file = st.file_uploader("Upload CSV file", type=["csv"])
if file is not None:
    if st.button("Predict for Batch", type='primary'):
        # 1. We make sure el puntero del archivo esté al inicio
        file.seek(0)
        
        # 2. Formateamos el archivo de forma robusta para Multipart Form-Data
        files = {"file": (file.name, file, "text/csv")}

        response = requests.post("https://cemoreno-superkartforecastingbackend.hf.space/v1/predictbatch", files=files)    # enter user name and space name before running the cell
        if response.status_code == 200:
            result = response.json()
            st.header("Batch Prediction Results")
            result_df = pd.DataFrame(result)
            st.dataframe(result_df) # Muestra una tabla interactiva
            #st.write(result)       # Imprime un bloque de texto JSON crudo en la pantalla
        else:
            st.error("Error making batch prediction")

st.success("SuperKart Sales Forecasting App is ready!")
