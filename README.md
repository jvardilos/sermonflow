# Quick and dirty readonly PCO

```
pip install -r requirements.txt 

python -m grpc_tools.protoc --proto_path=ProPresenter7-Proto/proto/google/protobuf --python_out=./pco_types/google/protobuf ProPresenter7-Proto/proto/google/protobuf/*.proto
```


```
python pipeline.py --skip-review --service-type Weekend   
```