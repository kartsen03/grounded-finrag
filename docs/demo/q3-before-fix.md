# Demo: Did Apple's revenue grow in fiscal 2022? Use the grounded-finrag tools and show me the evidence passages.

| | |
|---|---|
| Client | Claude Code 2.1.218 (`claude -p`, stream-json) |
| Model | `claude-sonnet-5-5` |
| MCP server | grounded-finrag over stdio, commit `be3a86e` |
| MCP SDK (server) | mcp 2.3.0 |
| Tools the model could use | `mcp__grounded-finrag__answer_question`, `mcp__grounded-finrag__list_filings`, `mcp__grounded-finrag__search_filings` (no built-in tools) |
| Run date (UTC) | 2026-11-25 |
| Duration | 16.9 s, 4 turns |

## User

> Did Apple's revenue grow in fiscal 2022? Use the grounded-finrag tools and show me the evidence passages.

## Assistant

I'll search the indexed filings for Apple's fiscal 2022 revenue evidence.

## Tool call 1: `mcp__grounded-finrag__search_filings`

```json
{
  "query": "Apple total net sales fiscal 2022 compared to fiscal 2021",
  "company": "Apple",
  "fiscal_year": 2022,
  "k": 5
}
```

## Tool call 2: `mcp__grounded-finrag__answer_question`

```json
{
  "question": "Did Apple's revenue grow in fiscal 2022 compared to fiscal 2021?",
  "company": "Apple"
}
```

### Tool error result

```
Error executing tool search_filings: {"error": {"code": "unknown_company", "message": "'Apple' does not match an indexed company. Call list_filings for the 32 indexed companies.", "retryable": false}}
```

### Tool error result

```
Error executing tool answer_question: {"error": {"code": "unknown_company", "message": "'Apple' does not match an indexed company. Call list_filings for the 32 indexed companies.", "retryable": false}}
```

## Assistant

Apple isn't recognized as a company name, so I'll check what's indexed.

## Tool call 3: `mcp__grounded-finrag__list_filings`

```json
{}
```

### Tool result

```json
{
  "count": 168,
  "companies": [
    "3M",
    "AES Corporation",
    "AMD",
    "Activision Blizzard",
    "Adobe",
    "Amazon",
    "Amcor",
    "American Express",
    "American Water Works",
    "Best Buy",
    "Block",
    "Boeing",
    "CVS Health",
    "Coca-Cola",
    "Corning",
    "Costco",
    "Foot Locker",
    "General Mills",
    "JPMorgan",
    "Johnson & Johnson",
    "Kraft Heinz",
    "Lockheed Martin",
    "MGM Resorts",
    "Microsoft",
    "Netflix",
    "Nike",
    "Paypal",
    "PepsiCo",
    "Pfizer",
    "Ulta Beauty",
    "Verizon",
    "Walmart"
  ],
  "filings": [
    {
      "doc_name": "3M_2018_10K",
      "company": "3M",
      "doc_type": "10-K",
      "fiscal_year": 2018,
      "fiscal_quarter": null,
      "chunks": 538
    },
    {
      "doc_name": "3M_2022_10K",
      "company": "3M",
      "doc_type": "10-K",
      "fiscal_year": 2022,
      "fiscal_quarter": null,
      "chunks": 808
    },
    {
      "doc_name": "3M_2023Q2_10Q",
      "company": "3M",
      "doc_type": "10-Q",
      "fiscal_year": 2023,
      "fiscal_quarter": 2,
      "chunks": 332
    },
    {
      "doc_name": "ACTIVISIONBLIZZARD_2019_10K",
      "company": "Activision Blizzard",
      "doc_type": "10-K",
      "fiscal_year": 2019,
      "fiscal_quarter": null,
      "chunks": 547
    },
    "... 164 more in the JSON transcript"
  ]
}
```

## Assistant

Apple isn't in the index, so I can't answer this with grounded evidence. Both lookups returned `unknown_company`, and `list_filings` shows 32 companies with no Apple (AAPL) filings of any year or form type. I have no passages to show you.

Apple's fiscal 2022 10-K would be the source for this, and I won't answer from memory because you asked for cited evidence.

Indexed companies with fiscal 2022 filings that I could run the same revenue-growth check on include Adobe, AMD, American Express, Boeing, Coca-Cola, Corning, CVS Health, General Mills, Johnson & Johnson, JPMorgan, Lockheed Martin, MGM Resorts, PayPal, PepsiCo, Verizon and 3M. If you want Apple covered, its 10-K would need to be added to the index first.
