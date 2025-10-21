#!/usr/bin/env python3
"""
Accrual Analysis Script

Usage:
    python run_accrual_analysis.py                           # Analyze all PO lines (3 workers)
    python run_accrual_analysis.py PO12345                   # Analyze specific PO
    python run_accrual_analysis.py --month "Feb 2025"        # Specify analysis month
    python run_accrual_analysis.py --workers 5               # Use 5 parallel workers
    python run_accrual_analysis.py --month "Oct 2025" --workers 5  # Combine options
"""

import sys
import os
import csv
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.logger import setup_logger
from src.clients.snowflake_data_client import SnowflakeDataClient
from src.processors.accrual_engine import AccrualEngine
from config.settings import CSV_RESULTS_DIR

logger = setup_logger(__name__)

# Lock for thread-safe console output
console_lock = Lock()


def get_analysis_month() -> str:
    """
    Prompt user to select the analysis month

    Returns:
        Month string in format "Month YYYY" (e.g., "October 2025")
    """
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    print("\n📅 SELECT ANALYSIS MONTH")
    print("=" * 80)

    # Generate list of months: current month + next 3 months + previous 3 months
    now = datetime.now()
    months = []
    for i in range(-3, 4):
        month_date = now + relativedelta(months=i)
        months.append(month_date.strftime("%B %Y"))

    # Display options
    for idx, month in enumerate(months, 1):
        marker = " ← Current Month" if idx == 4 else ""
        print(f"  {idx}. {month}{marker}")

    print(f"  8. Enter custom month")
    print("=" * 80)

    while True:
        choice = input("\nSelect option (1-8): ").strip()

        if choice.isdigit():
            choice_num = int(choice)
            if 1 <= choice_num <= 7:
                selected = months[choice_num - 1]
                print(f"\n✓ Selected: {selected}")
                return selected
            elif choice_num == 8:
                custom = input("\nEnter month (e.g., 'October 2025'): ").strip()
                # Validate format
                try:
                    datetime.strptime(custom, "%B %Y")
                    print(f"\n✓ Selected: {custom}")
                    return custom
                except ValueError:
                    print("❌ Invalid format. Please use format: 'October 2025'")
                    continue

        print("❌ Invalid choice. Please select 1-8.")


def process_single_po(po_line: dict, bills_by_po: dict, accrual_engine: AccrualEngine,
                       index: int, total: int) -> tuple:
    """
    Process a single PO line for accrual analysis

    Args:
        po_line: PO line data
        bills_by_po: Dictionary of bills grouped by PO
        accrual_engine: AccrualEngine instance
        index: Current index
        total: Total number of POs

    Returns:
        Tuple of (po_line, decision, analysis_time)
    """
    po_num = po_line.get('PO_NUMBER')
    vendor = po_line.get('VENDOR_NAME', 'Unknown')
    description = po_line.get('DESCRIPTION', '')[:50]

    # Get related bills for this PO from in-memory lookup
    related_bills = bills_by_po.get(po_num, [])

    # Thread-safe console output for start
    with console_lock:
        print(f"\n[{index}/{total}] PO: {po_num}")
        print(f"   Vendor: {vendor}")
        print(f"   Description: {description}...")
        print(f"   Related bills: {len(related_bills)}")
        print("-" * 60)

    # Analyze
    start_time = time.time()
    decision = accrual_engine.analyze_po_line(po_line, related_bills)
    analysis_time = time.time() - start_time

    # Thread-safe console output for result
    with console_lock:
        if decision.needs_accrual:
            print(f"   [{po_num}] ✅ ACCRUAL NEEDED")
            print(f"   [{po_num}] 💰 Amount: {decision.accrual_amount:,.2f} {po_line.get('FOREIGN_CURRENCY', '')}")
        else:
            print(f"   [{po_num}] ⭕ No accrual needed")

        print(f"   [{po_num}] 📝 Reasoning: {decision.reasoning[:80]}...")
        print(f"   [{po_num}] 🎯 Confidence: {decision.confidence_score:.2%}")
        print(f"   [{po_num}] ⏱️  Analysis time: {analysis_time:.1f}s")

        if decision.tokens_total > 0:
            print(f"   [{po_num}] 🪙 Tokens: {decision.tokens_total:,} (input: {decision.tokens_input:,}, output: {decision.tokens_output:,})")

    return (po_line, decision, analysis_time)


def run_accrual_analysis(po_number: str = None, analysis_month: str = None, max_workers: int = 3):
    """
    Run accrual analysis on PO lines

    Args:
        po_number: Optional specific PO to analyze
        analysis_month: Optional month to analyze for (e.g., "February 2025")
        max_workers: Number of parallel workers (default: 3)
    """
    # Start timing
    script_start_time = time.time()

    try:
        print("=" * 80)
        print("🔍 ACCRUAL ANALYSIS")
        print("=" * 80)

        # Get analysis month if not provided
        if not analysis_month:
            analysis_month = get_analysis_month()

        # Initialize clients
        print("\n📊 Connecting to Snowflake...")
        snowflake_client = SnowflakeDataClient()

        print(f"🤖 Initializing AI Accrual Engine...")
        accrual_engine = AccrualEngine(current_month=analysis_month)
        print(f"   Analysis month: {accrual_engine.current_month}")

        # Get PO lines to analyze
        print("\n📥 Fetching PO lines from Snowflake...")
        po_lines = snowflake_client.get_po_lines_for_accrual_analysis()

        if not po_lines:
            print("❌ No PO lines found in Snowflake view")
            return

        # Filter to specific PO if requested
        if po_number:
            po_lines = [po for po in po_lines if po.get('PO_NUMBER') == po_number]
            if not po_lines:
                print(f"❌ PO {po_number} not found in analysis view")
                return
            print(f"✓ Found PO {po_number}")
        else:
            print(f"✓ Found {len(po_lines)} PO lines to analyze")

        # Get ALL related bills once and store in memory
        print("📥 Fetching all related bills from Snowflake...")
        bills_by_po = snowflake_client.get_all_related_bills()
        print(f"✓ Loaded bills for {len(bills_by_po)} POs")

        # Check which PO lines have already been analyzed for this month
        print(f"🔍 Checking for already-analyzed PO lines for {analysis_month}...")
        analyzed_lookup_keys = snowflake_client.get_analyzed_po_lines_for_month(analysis_month)
        print(f"✓ Found {len(analyzed_lookup_keys)} PO lines already analyzed for this month")

        # Filter out already-analyzed PO lines
        po_lines_before = len(po_lines)
        po_lines = [po for po in po_lines if po.get('LOOKUP_KEY') not in analyzed_lookup_keys]
        skipped_count = po_lines_before - len(po_lines)

        if skipped_count > 0:
            print(f"⏭️  Skipping {skipped_count} already-analyzed PO lines")

        if not po_lines:
            print(f"\n✅ All {po_lines_before} PO lines have already been analyzed for {analysis_month}")
            print(f"   No new analysis needed!")
            return

        print(f"✓ {len(po_lines)} PO lines need analysis")

        # Prepare CSV output
        csv_path = CSV_RESULTS_DIR / "accrual_analysis_results.csv"
        results_data = []

        # Clear CSV file at start
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            fieldnames = ['lookup_key', 'po_number', 'vendor_name', 'gl_account', 'description',
                         'total_amount', 'billed_amount', 'unbilled_amount', 'currency',
                         'needs_accrual', 'accrual_amount', 'short_summary', 'reasoning', 'confidence_score',
                         'analysis_month', 'analyzed_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        logger.info("Cleared CSV file for fresh run")

        print("\n" + "=" * 80)
        print(f"🔬 ANALYZING PO LINES (Parallel workers: {max_workers})")
        print("=" * 80)

        # Analyze PO lines in parallel
        total_analyzed = 0
        total_accruals_needed = 0
        total_tokens_input = 0
        total_tokens_output = 0
        total_tokens_total = 0
        total_ai_time = 0.0

        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_index = {}
            for i, po_line in enumerate(po_lines, 1):
                future = executor.submit(
                    process_single_po,
                    po_line,
                    bills_by_po,
                    accrual_engine,
                    i,
                    len(po_lines)
                )
                future_to_index[future] = i

            # Collect results as they complete
            for future in as_completed(future_to_index):
                try:
                    po_line, decision, analysis_time = future.result()
                    po_num = po_line.get('PO_NUMBER')
                    vendor = po_line.get('VENDOR_NAME', 'Unknown')

                    # Update counters
                    if decision.needs_accrual:
                        total_accruals_needed += 1

                    total_analyzed += 1
                    total_tokens_input += decision.tokens_input
                    total_tokens_output += decision.tokens_output
                    total_tokens_total += decision.tokens_total
                    total_ai_time += decision.processing_time_seconds

                    # Add to results
                    # Add single quote prefix to analysis_month to force Excel to treat as text
                    analysis_month_text = f"'{accrual_engine.current_month}"

                    results_data.append({
                        'lookup_key': po_line.get('LOOKUP_KEY', ''),
                        'po_number': po_num,
                        'vendor_name': vendor,
                        'gl_account': po_line.get('GL_ACCOUNT_NAME', ''),
                        'description': po_line.get('DESCRIPTION', ''),
                        'total_amount': po_line.get('TOTAL_AMOUNT_FOREIGN', ''),
                        'billed_amount': po_line.get('BILLED_AMOUNT_FOREIGN', ''),
                        'unbilled_amount': po_line.get('UNBILLED_AMOUNT_FOREIGN', ''),
                        'currency': po_line.get('FOREIGN_CURRENCY', ''),
                        'needs_accrual': decision.needs_accrual,
                        'accrual_amount': decision.accrual_amount if decision.needs_accrual else 0,
                        'short_summary': decision.short_summary,
                        'reasoning': decision.reasoning,
                        'confidence_score': decision.confidence_score,
                        'analysis_month': analysis_month_text,
                        'analyzed_at': decision.analyzed_at.isoformat()
                    })

                except Exception as e:
                    logger.error(f"Error processing PO in parallel: {str(e)}")
                    print(f"❌ Error processing a PO: {str(e)}")

        # Save results to CSV
        if results_data:
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ['lookup_key', 'po_number', 'vendor_name', 'gl_account', 'description',
                             'total_amount', 'billed_amount', 'unbilled_amount', 'currency',
                             'needs_accrual', 'accrual_amount', 'short_summary', 'reasoning', 'confidence_score',
                             'analysis_month', 'analyzed_at']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results_data)

        # Calculate total execution time
        total_execution_time = time.time() - script_start_time
        minutes = int(total_execution_time // 60)
        seconds = int(total_execution_time % 60)

        # Print summary
        print("\n" + "=" * 80)
        print("📊 ANALYSIS SUMMARY")
        print("=" * 80)
        print(f"  Analysis month: {accrual_engine.current_month}")
        print(f"  Total PO lines found: {po_lines_before}")
        print(f"  Already analyzed (skipped): {skipped_count}")
        print(f"  Newly analyzed: {total_analyzed}")
        print(f"  ")
        print(f"  Accruals needed: {total_accruals_needed}")
        print(f"  No accrual needed: {total_analyzed - total_accruals_needed}")
        print(f"  ")
        print(f"  Total tokens used: {total_tokens_total:,}")
        print(f"    - Input tokens: {total_tokens_input:,}")
        print(f"    - Output tokens: {total_tokens_output:,}")
        print(f"  Average tokens per analysis: {total_tokens_total / max(total_analyzed, 1):,.0f}")
        print(f"  ")
        print(f"  Total execution time: {minutes}m {seconds}s")
        avg_time = total_ai_time / max(total_analyzed, 1)
        print(f"  Average time per PO: {avg_time:.1f}s")
        print("=" * 80)
        print(f"\n✓ Results saved to CSV: {csv_path.absolute()}")
        print(f"\n💡 Next step: Review the CSV and update Google Sheets or Snowflake")
        print("=" * 80)
        print("🎯 Analysis completed!")

        logger.info(f"Accrual analysis completed: {total_analyzed} PO lines, {total_accruals_needed} accruals needed, "
                   f"{total_tokens_total:,} tokens, {minutes}m {seconds}s")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        logger.error(f"Error in accrual analysis: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Parse command line arguments
    po_number = None
    analysis_month = None
    max_workers = 3  # Default: 3 parallel workers

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--month" and i + 1 < len(sys.argv):
            analysis_month = sys.argv[i + 1]
            i += 2
        elif arg == "--workers" and i + 1 < len(sys.argv):
            max_workers = int(sys.argv[i + 1])
            i += 2
        elif not arg.startswith("--"):
            po_number = arg
            i += 1
        else:
            i += 1

    run_accrual_analysis(po_number=po_number, analysis_month=analysis_month, max_workers=max_workers)
