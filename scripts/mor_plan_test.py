import logging, os
from pyiceberg.catalog import load_catalog

# HTTP-level logging so we can see whether /plan is hit
logging.basicConfig(level=logging.DEBUG)

catalog = load_catalog(
    "irc",
    **{
        "type": "rest",
        "uri": os.environ["IRC_URI"],
        "s3.access-key-id":     os.environ["AWS_ACCESS_KEY_ID"],
        "s3.secret-access-key": os.environ["AWS_SECRET_ACCESS_KEY"],
        "s3.region":            os.environ["AWS_REGION"],
    },
)

table = catalog.load_table("test_mor.taxi_mor")
scan  = table.scan()

tasks = list(scan.plan_files())
print(f"\n=== plan_files() returned {len(tasks)} task(s) ===")
for t in tasks:
    print(f"  data file: {t.file.file_path}")
    print(f"    records: {t.file.record_count}")
    print(f"    delete files attached: {len(t.delete_files)}")
    for df in t.delete_files:
        print(f"      - {df.file_path}")
        print(f"        content={df.content}  records={df.record_count}")

arrow_tbl = scan.to_arrow()
print(f"\n=== to_arrow() returned {arrow_tbl.num_rows} row(s) ===")
print(f"Expected: 3  (ids 1, 3, 5 after deleting 2 and 4)")
print(arrow_tbl.to_pandas())
