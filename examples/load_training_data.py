import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diablos_data import load_model_data, connect

X,y,metadata=load_model_data(feature_set='stuff',target='y_event',split='train')
print('Training shape:', X.shape)
print('Predictors:', list(X.columns))
print('Target counts:', y.value_counts().to_dict())
# Fit encoders, imputers and scalers on X_train only. Never fit on test data.
# Keep metadata separate from predictors for grouped validation and audit.
with connect() as db:
    print(db.execute('SELECT * FROM summary_year ORDER BY year').df().to_string(index=False))
