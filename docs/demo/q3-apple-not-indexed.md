# Demo: Did Apple's revenue grow in fiscal 2022? Use the grounded-finrag tools and show me the evidence passages.

| | |
|---|---|
| Client | Claude Code 2.1.218 (`claude -p`, stream-json) |
| Model | `claude-sonnet-5-5` |
| MCP server | grounded-finrag over stdio, commit `5345522` |
| MCP SDK (server) | mcp 2.3.0 |
| Tools the model could use | `mcp__grounded-finrag__answer_question`, `mcp__grounded-finrag__list_filings`, `mcp__grounded-finrag__search_filings` (no built-in tools) |
| Run date (UTC) | 2026-11-25 |
| Duration | 17.3 s, 4 turns |

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

Apple didn't match an indexed company name, so I'll check the filings list.

## Tool call 3: `mcp__grounded-finrag__list_filings`

```json
{}
```

### Tool result

```json
{
  "count": 84,
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
    "... 80 more in the JSON transcript"
  ]
}
```

## Assistant

I can't show evidence passages for this, because Apple isn't in the index. Both tools rejected "Apple" as an unknown company. `list_filings` shows 84 filings covering 32 companies, and Apple has no 10-K, 10-Q, 8-K or earnings release among them.

I didn't search without a company filter. That would only return passages from other companies, and none of them could support a claim about Apple.

From my own general knowledge, which is not grounded in these tools, Apple's fiscal 2022 net sales rose about 8% over fiscal 2021. I haven't verified that against a filing.

If you want to stay within the index, here are two options:
- **Another company:** the index has fiscal 2022 10-Ks for Adobe, AMD, Amazon (2017 and 2019 only), Boeing, Coca-Cola, Corning, Lockheed Martin, PayPal, Verizon and others, so I can run the same revenue-growth check on one of those.
- **Apple filings:** you could add Apple's fiscal 2022 10-K to the index, and then I could rerun this question.
