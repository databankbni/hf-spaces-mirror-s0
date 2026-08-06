import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE

# load data
df = pd.read_csv("heart-new.csv")

# target
y = df["HeartDisease"]
X = df.drop("HeartDisease", axis=1)

# encode categorical
label_encoders = {}
for col in X.select_dtypes(include=['object']).columns:
    le = LabelEncoder()
    X[col] = le.fit_transform(X[col])
    label_encoders[col] = le

# balance data
smote = SMOTE()
X_resampled, y_resampled = smote.fit_resample(X, y)

# split
X_train, X_test, y_train, y_test = train_test_split(
    X_resampled, y_resampled, test_size=0.2, random_state=42
)

# pipeline
pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("model", RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        random_state=42
    ))
])

# train
pipeline.fit(X_train, y_train)

# save everything
joblib.dump(pipeline, "new_pipeline.pkl")
joblib.dump(label_encoders, "new_label_encoders.pkl")
joblib.dump(X.columns.tolist(), "new_model_columns.pkl")

print("✅ Model trained and saved successfully!")