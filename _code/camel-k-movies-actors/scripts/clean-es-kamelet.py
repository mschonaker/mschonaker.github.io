import sys, yaml

data = yaml.safe_load(sys.stdin)

# remove empty step {}
data["spec"]["template"]["from"]["steps"] = [
    s for s in data["spec"]["template"]["from"]["steps"] if s != {}
]

# clean metadata keys that belong to the operator
for k in ["creationTimestamp", "generation", "ownerReferences", "resourceVersion", "uid"]:
    data["metadata"].pop(k, None)

data["metadata"]["labels"] = {"camel.apache.org/kamelet.type": "sink"}
data["metadata"]["annotations"] = {
    "camel.apache.org/provider": "Apache Software Foundation",
    "camel.apache.org/kamelet.group": "ElasticSearch",
    "camel.apache.org/kamelet.namespace": "Search",
}
data.pop("status", None)

sys.stdout.write(yaml.dump(data, default_flow_style=False))
