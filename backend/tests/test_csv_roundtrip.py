import csv
import io

def test_csv_roundtrip_with_commas_and_newlines():
    # Simulate survey input with complex quoted strings, commas, newlines, and IDs
    original_data = [
        {"id": "RESP_001", "comment": "Loved the cappuccino, but $7.50 is steep!", "rating": "4"},
        {"id": "RESP_002", "comment": "Line 1: Coffee was okay.\nLine 2: Barista was very friendly.", "rating": "5"},
        {"id": "RESP_003", "comment": "Found \"hair\" in my pastry, gross!", "rating": "1"},
        {"id": "RESP_004", "comment": "", "rating": "3"} # Blank comment edge case
    ]

    output_stream = io.StringIO()
    writer = csv.DictWriter(output_stream, fieldnames=["id", "comment", "rating"], quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for row in original_data:
        writer.writerow(row)

    csv_text = output_stream.getvalue()

    # Read back and verify strict preservation
    input_stream = io.StringIO(csv_text)
    reader = csv.DictReader(input_stream)
    recovered_rows = list(reader)

    assert len(recovered_rows) == 4
    assert recovered_rows[0]["id"] == "RESP_001"
    assert recovered_rows[0]["comment"] == "Loved the cappuccino, but $7.50 is steep!"
    assert recovered_rows[1]["comment"] == "Line 1: Coffee was okay.\nLine 2: Barista was very friendly."
    assert recovered_rows[2]["comment"] == "Found \"hair\" in my pastry, gross!"
    assert recovered_rows[3]["comment"] == ""
