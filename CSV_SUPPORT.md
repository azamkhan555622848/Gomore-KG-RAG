# CSV Support Documentation

## Overview

The Gomore Knowledge Graph RAG System now supports CSV files as input documents. CSV files are automatically converted to structured text format that can be processed by the entity extraction and graph building pipeline.

## How CSV Files Are Processed

### 1. Loading

When a CSV file is loaded:
- The system reads the file using pandas with UTF-8 encoding (fallback to latin-1)
- Empty files are handled gracefully
- Bad lines are skipped automatically

### 2. Text Conversion

Each CSV file is converted to structured text in the following format:

```
CSV Document: filename.csv
Columns: Column1, Column2, Column3

Row 1: Column1: value1; Column2: value2; Column3: value3
Row 2: Column1: value4; Column2: value5; Column3: value6
...
```

### 3. Entity Extraction

The structured text is processed like any other document:
- Entities are extracted from column names and values
- Relationships between entities are identified
- Each row becomes searchable content in the knowledge graph

## Usage

### Adding CSV Files

Simply place your CSV files in the `documents/` directory:

```bash
documents/
├── my_data.csv
├── products.csv
└── customers.csv
```

### Running the Build Pipeline

No special configuration needed - CSV files are processed automatically:

```bash
python scripts/build_graph.py
```

The system will:
1. Detect all `.csv` files in the documents directory
2. Convert them to structured text
3. Extract entities and relationships
4. Include them in the knowledge graph

### Querying CSV Data

Once built, you can query the CSV data like any other document:

```python
from query_phase.graph_rag_engine import GraphRAGEngine

engine = GraphRAGEngine()

# Query CSV content
result = engine.query("What products are in the database?")
print(result.answer)
```

## Example CSV File

**products.csv**:
```csv
Product ID,Product Name,Category,Price,Stock
P001,Laptop,Electronics,999.99,50
P002,Mouse,Electronics,29.99,200
P003,Desk Chair,Furniture,299.99,30
```

**Converted Text**:
```
CSV Document: products.csv
Columns: Product ID, Product Name, Category, Price, Stock

Row 1: Product ID: P001; Product Name: Laptop; Category: Electronics; Price: 999.99; Stock: 50
Row 2: Product ID: P002; Product Name: Mouse; Category: Electronics; Price: 29.99; Stock: 200
Row 3: Product ID: P003; Product Name: Desk Chair; Category: Furniture; Price: 299.99; Stock: 30
```

**Extracted Entities** (examples):
- Laptop (PRODUCT)
- Electronics (CONCEPT)
- Mouse (PRODUCT)
- Desk Chair (PRODUCT)
- Furniture (CONCEPT)

**Extracted Relationships** (examples):
- Laptop → PART_OF → Electronics
- Mouse → PART_OF → Electronics
- Desk Chair → PART_OF → Furniture

## Best Practices

### 1. Clean Data

- Remove special characters from column names
- Use descriptive column names (they become entities)
- Ensure consistent data types within columns

### 2. File Size

- Keep CSV files under 10MB for optimal performance
- Large files (>10MB) may be slow to process
- Consider splitting very large CSVs into smaller files

### 3. Column Design

- Use meaningful column names (e.g., "Product Name" instead of "col1")
- Include descriptive columns that help entity extraction
- Avoid too many columns (>20) as it creates verbose text

### 4. Missing Values

- Missing values (NaN) are automatically skipped
- Empty cells won't appear in the converted text
- This helps keep the text clean and focused

## Limitations

### Current Limitations

1. **No Table Structure**: CSV structure is flattened to text
   - Table relationships are not preserved
   - Row order is maintained but not explicitly linked

2. **No Data Type Inference**: All values treated as text
   - Numeric relationships (e.g., "greater than") not extracted
   - Dates are treated as strings

3. **Large Files**: Performance degrades with very large CSVs
   - Recommendation: <10,000 rows per file
   - Consider aggregating or sampling large datasets

### Future Enhancements

Planned improvements:
- [ ] Preserve table structure in graph
- [ ] Extract numeric relationships
- [ ] Date/time entity recognition
- [ ] Column relationship inference
- [ ] Multi-table join support

## Troubleshooting

### Issue: CSV file not loading

**Cause**: Encoding issues
**Solution**: Save CSV as UTF-8 with BOM or try latin-1 encoding

### Issue: Strange characters in output

**Cause**: Incorrect encoding detection
**Solution**: Manually specify encoding in the code if needed

### Issue: Too many entities extracted

**Cause**: CSV has many unique values
**Solution**:
- Filter or aggregate data before creating CSV
- Adjust `max_entities_per_chunk` in config

### Issue: Poor query results for CSV data

**Cause**: Flat text structure loses relationships
**Solution**:
- Add contextual columns that describe relationships
- Use more descriptive column names and values

## Configuration

### CSV-Specific Settings

Located in `shared/config.py`:

```python
# Already configured
supported_formats: List[str] = ['.pdf', '.docx', '.txt', '.md', '.csv']

# Chunk size affects how CSV rows are grouped
chunk_size: int = 512  # Adjust if needed for large CSVs
```

### Adjusting for CSV Files

For CSV-heavy workloads:

```python
# Increase chunk size to fit more rows per chunk
update_config('build', chunk_size=1024)

# Increase entity limit if CSV has many columns
update_config('build', max_entities_per_chunk=30)
```

## Example Workflow

### Complete Example

1. **Prepare CSV data**:
```bash
# Create a sample CSV
cat > documents/sample_data.csv << EOF
Name,Role,Department,Location
Alice Smith,Engineer,IT,New York
Bob Jones,Manager,Sales,London
Carol White,Designer,Marketing,Tokyo
EOF
```

2. **Build knowledge graph**:
```bash
python scripts/build_graph.py
```

3. **Query the data**:
```python
from query_phase.graph_rag_engine import GraphRAGEngine

engine = GraphRAGEngine()

# Query about people
result = engine.query("Who works in IT?")
print(result.answer)
# Expected: Information about Alice Smith

# Query about locations
result = engine.query("What departments are in London?")
print(result.answer)
# Expected: Information about Sales department
```

## Integration with Other Formats

CSV files work seamlessly with other document types:

```bash
documents/
├── company_overview.pdf      # Company information
├── employee_handbook.docx    # Policies
├── employees.csv             # Employee data
└── org_chart.md              # Organization structure
```

The system will:
- Extract entities from all formats
- Link related entities across documents
- Enable cross-document queries

Example query: *"What is Alice Smith's role according to the employee handbook?"*
- Uses: employees.csv (for Alice's role) + employee_handbook.docx (for role descriptions)

## Performance Tips

### Optimization for Large CSVs

1. **Pre-process data**:
   - Remove duplicate rows
   - Filter irrelevant columns
   - Aggregate when possible

2. **Chunk strategically**:
   - Adjust chunk_size based on row length
   - Aim for 10-20 rows per chunk

3. **Monitor build time**:
   - CSV processing is fast (~1-2s per 1000 rows)
   - Entity extraction is the bottleneck (~70ms per chunk)

### Example: 10,000 row CSV

- Loading: ~5 seconds
- Text conversion: ~10 seconds
- Chunking (20 rows/chunk): ~500 chunks
- Entity extraction: ~35 seconds (500 chunks × 70ms)
- **Total**: ~50 seconds

## Summary

CSV support enables:
✅ Structured data import
✅ Entity extraction from tabular data
✅ Relationship discovery across rows
✅ Cross-document knowledge graph queries
✅ Unified querying of documents + data

The system automatically handles:
✅ Encoding detection
✅ Missing value handling
✅ Text normalization
✅ Chunking and embedding

Just add CSV files to `documents/` and build!
