# sentinel:skip-file — hardcoded paths are fixture/registry/audit-narrative data for this repo's research workflow, not portable application configuration. Same pattern as push_all_repos.py and E156 workbook files.
"""
LEC Evidence Synthesis Tool v2.0 - Full Pipeline Selenium Test Suite
Comprehensive testing of:
1. All UI elements
2. Topic selector (370 topics)
3. CT.gov automated search
4. PubMed cross-validation
5. Data extraction
6. Meta-analysis pipeline
7. Validation against published meta-analyses
"""

import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import time
import json
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
import os

class LECFullPipelineTester:
    """Comprehensive test suite for LEC Evidence Synthesis Tool"""

    # ESC Guideline Validation Data - All topics with 4+ RCTs (2012-2026)
    # Reference: esc_guidelines_validation_data.json
    VALIDATION_DATA = {
        # Heart Failure Topics
        'sglt2i': {
            'name': 'SGLT2 Inhibitors in Heart Failure',
            'reference': 'Vaduganathan 2022 (Lancet)',
            'guideline': 'ESC HF 2021/2023',
            'n_rcts': 5,
            'expected_hr': 0.77,
            'expected_ci_low': 0.72,
            'expected_ci_high': 0.82,
            'expected_i2': 0,
            'tolerance': 0.02
        },
        'betablocker': {
            'name': 'Beta-Blockers in Heart Failure',
            'reference': 'Lechat 1998 (Circulation)',
            'guideline': 'ESC HF 2021/2023',
            'n_rcts': 5,
            'expected_or': 0.66,
            'expected_ci_low': 0.58,
            'expected_ci_high': 0.75,
            'expected_i2': 0,
            'tolerance': 0.03
        },
        'acei': {
            'name': 'ACE Inhibitors in Heart Failure',
            'reference': 'Garg & Yusuf 1995 (JAMA)',
            'guideline': 'ESC HF 2021/2023',
            'n_rcts': 5,
            'expected_or': 0.77,
            'expected_ci_low': 0.67,
            'expected_ci_high': 0.88,
            'expected_i2': 15,
            'tolerance': 0.03
        },
        'mra': {
            'name': 'MRA in Heart Failure',
            'reference': 'Burnett 2017 (BMC Cardiovasc)',
            'guideline': 'ESC HF 2021/2023',
            'n_rcts': 4,
            'expected_hr': 0.81,
            'expected_ci_low': 0.75,
            'expected_ci_high': 0.87,
            'expected_i2': 0,
            'tolerance': 0.03
        },
        'arni': {
            'name': 'ARNI in Heart Failure',
            'reference': 'Wang 2020 (ESC HF)',
            'guideline': 'ESC HF 2021/2023',
            'n_rcts': 4,
            'expected_hr': 0.84,
            'expected_ci_low': 0.78,
            'expected_ci_high': 0.90,
            'expected_i2': 45,
            'tolerance': 0.04
        },
        # Atrial Fibrillation
        'doac': {
            'name': 'DOACs in Atrial Fibrillation',
            'reference': 'Ruff 2014 (Lancet)',
            'guideline': 'ESC AF 2020/2024',
            'n_rcts': 4,
            'expected_rr': 0.81,
            'expected_ci_low': 0.73,
            'expected_ci_high': 0.91,
            'expected_i2': 47,
            'tolerance': 0.04
        },
        # Coronary Artery Disease
        'colchicine': {
            'name': 'Colchicine for CVD Prevention',
            'reference': 'Nidorf 2020 (NEJM)',
            'guideline': 'ESC CCS 2024',
            'n_rcts': 4,
            'expected_hr': 0.72,
            'expected_ci_low': 0.65,
            'expected_ci_high': 0.80,
            'expected_i2': 32,
            'tolerance': 0.05
        },
        'dapt': {
            'name': 'DAPT (P2Y12 inhibitors) in ACS',
            'reference': 'Capodanno 2021 (JACC)',
            'guideline': 'ESC ACS 2020/2023',
            'n_rcts': 4,
            'expected_hr': 0.82,
            'expected_ci_low': 0.77,
            'expected_ci_high': 0.88,
            'expected_i2': 25,
            'tolerance': 0.03
        },
        # Diabetes/Cardiometabolic
        'glp1ra': {
            'name': 'GLP-1 RAs in Diabetes/CVD',
            'reference': 'Sattar 2021 (Lancet DE)',
            'guideline': 'ESC Diabetes 2019/2023',
            'n_rcts': 8,
            'expected_hr': 0.86,
            'expected_ci_low': 0.80,
            'expected_ci_high': 0.93,
            'expected_i2': 0,
            'tolerance': 0.02
        },
        # Lipid Management
        'statins': {
            'name': 'Statins for CV Prevention',
            'reference': 'CTT Collaboration 2010 (Lancet)',
            'guideline': 'ESC Dyslipidaemia 2019/2021',
            'n_rcts': 26,
            'expected_rr': 0.79,
            'expected_ci_low': 0.77,
            'expected_ci_high': 0.81,
            'expected_i2': 10,
            'tolerance': 0.02
        },
        # Sudden Cardiac Death
        'icd': {
            'name': 'ICD for Primary Prevention',
            'reference': 'Stavrakis 2017 (EHJ)',
            'guideline': 'ESC VA 2022',
            'n_rcts': 5,
            'expected_hr': 0.75,
            'expected_ci_low': 0.64,
            'expected_ci_high': 0.88,
            'expected_i2': 35,
            'tolerance': 0.04
        },
        # Pericardial Disease
        'pericarditis': {
            'name': 'Colchicine for Pericarditis',
            'reference': 'Imazio 2013 (JACC)',
            'guideline': 'ESC Pericarditis 2015/2025',
            'n_rcts': 4,
            'expected_rr': 0.43,
            'expected_ci_low': 0.32,
            'expected_ci_high': 0.58,
            'expected_i2': 0,
            'tolerance': 0.05
        }
    }

    def __init__(self):
        self.results = {
            'ui_tests': [],
            'topic_tests': [],
            'search_tests': [],
            'pipeline_tests': [],
            'validation_tests': []
        }
        self.passed = 0
        self.failed = 0
        self.topics_tested = 0
        self.start_time = None

    def setup(self):
        """Initialize Chrome browser"""
        print("=" * 70)
        print("LEC Evidence Synthesis Tool v2.0 - Full Pipeline Test Suite")
        print("=" * 70)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        options = Options()
        # options.add_argument('--headless')  # Uncomment for headless
        options.add_argument('--start-maximized')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        # Enable browser logging
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 15)

        file_path = os.path.abspath(r"C:\Users\user\Downloads\lec_phase0_project\lec-web\lec-evidence-synthesis-v2.html")
        self.driver.get(f"file:///{file_path}")
        time.sleep(2)

        self.start_time = time.time()
        print(f"\n[OK] Opened: {file_path}\n")

    def log_test(self, category, test_name, passed, details=""):
        """Log test result"""
        status = "[PASS]" if passed else "[FAIL]"
        result = {
            "test": test_name,
            "passed": passed,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.results[category].append(result)

        if passed:
            self.passed += 1
        else:
            self.failed += 1

        print(f"  {status}: {test_name}" + (f" - {details}" if details else ""))

    def click_element(self, element):
        """Safe click using JavaScript"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.3)
            self.driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e:
            return False

    def click_tab(self, tab_name):
        """Click navigation tab"""
        try:
            tab = self.driver.find_element(By.XPATH, f"//button[@data-tab='{tab_name}']")
            self.click_element(tab)
            time.sleep(0.5)
            return True
        except:
            return False

    def print_browser_logs(self, filter_prefix=None):
        """Print browser console logs, optionally filtered by prefix"""
        try:
            logs = self.driver.get_log('browser')
            for entry in logs:
                msg = entry.get('message', '')
                if filter_prefix is None or filter_prefix in msg:
                    level = entry.get('level', 'INFO')
                    print(f"    [{level}] {msg[:200]}")
        except Exception as e:
            print(f"    [Could not get browser logs: {e}]")

    # =========================================================================
    # PART 1: UI Element Tests
    # =========================================================================

    def test_ui_elements(self):
        """Test all UI elements exist and are functional"""
        print("\n" + "=" * 70)
        print("PART 1: UI ELEMENT TESTS")
        print("=" * 70)

        # Test page load
        print("\n[1.1] Page Load")
        title = self.driver.title
        self.log_test('ui_tests', "Page title present", "LEC" in title, title)

        header = self.driver.find_element(By.TAG_NAME, "h1")
        self.log_test('ui_tests', "Header correct", "LEC Evidence Synthesis Tool" in header.text)

        badge = self.driver.find_element(By.CLASS_NAME, "header-badge")
        self.log_test('ui_tests', "Version badge v2.0", "2.0" in badge.text)

        # Test navigation tabs
        print("\n[1.2] Navigation Tabs")
        tabs = ['discovery', 'data', 'meta', 'grade', 'nma', 'subgroups', 'recommendation', 'sof', 'validation', 'export']
        for tab in tabs:
            success = self.click_tab(tab)
            content = self.driver.find_element(By.ID, f"tab-{tab}")
            is_active = "active" in content.get_attribute("class")
            self.log_test('ui_tests', f"Tab '{tab}' works", success and is_active)

        # Test Discovery tab elements
        print("\n[1.3] Discovery Tab Elements")
        self.click_tab('discovery')
        time.sleep(0.5)

        elements = {
            'esc-category-select': 'Category selector',
            'esc-topic-select': 'Topic selector',
            'btn-load-topic': 'Load Topic button',
            'ctg-condition': 'Condition input',
            'ctg-intervention': 'Intervention input',
            'ctg-study-type': 'Study type dropdown',
            'ctg-status': 'Status dropdown',
            'ctg-phase': 'Phase dropdown',
            'ctg-results': 'Has results dropdown',
            'ctg-min-enrollment': 'Min enrollment input',
            'btn-search-ctgov': 'Search CT.gov button',
            'pubmed-query': 'PubMed query input'
        }

        for elem_id, name in elements.items():
            try:
                elem = self.driver.find_element(By.ID, elem_id)
                self.log_test('ui_tests', f"{name} present", elem.is_displayed() or elem.is_enabled())
            except:
                self.log_test('ui_tests', f"{name} present", False, "Not found")

        # Test Data tab elements
        print("\n[1.4] Data Tab Elements")
        self.click_tab('data')
        time.sleep(0.5)

        data_elements = {
            'pico-title': 'PICO Title',
            'pico-population': 'PICO Population',
            'pico-intervention': 'PICO Intervention',
            'pico-comparator': 'PICO Comparator',
            'pico-outcome': 'PICO Outcome',
            'effect-measure': 'Effect measure dropdown',
            'study-design': 'Study design dropdown',
            'study-data': 'Study data textarea',
            'btn-parse-data': 'Parse Data button',
            'btn-clear-data': 'Clear button',
            'btn-load-sglt2i': 'SGLT2i sample button',
            'btn-load-pcsk9i': 'PCSK9i sample button',
            'btn-load-colchicine': 'Colchicine sample button'
        }

        for elem_id, name in data_elements.items():
            try:
                elem = self.driver.find_element(By.ID, elem_id)
                self.log_test('ui_tests', f"{name} present", elem.is_displayed() or elem.is_enabled())
            except:
                self.log_test('ui_tests', f"{name} present", False, "Not found")

        # Test Meta-Analysis tab elements
        print("\n[1.5] Meta-Analysis Tab Elements")
        self.click_tab('meta')
        time.sleep(0.5)

        meta_elements = {
            'ma-model': 'Model dropdown',
            'tau-estimator': 'Tau estimator dropdown',
            'btn-run-meta': 'Run Meta-Analysis button',
            'pooled-estimate': 'Pooled estimate display',
            'pooled-ci': 'Pooled CI display',
            'stat-i2': 'I-squared statistic display',
            'stat-tau2': 'tau-squared statistic display',
            'forest-plot': 'Forest plot SVG',
            'funnel-plot': 'Funnel plot SVG'
        }

        for elem_id, name in meta_elements.items():
            try:
                elem = self.driver.find_element(By.ID, elem_id)
                self.log_test('ui_tests', f"{name} present", True)
            except:
                self.log_test('ui_tests', f"{name} present", False, "Not found")

    # =========================================================================
    # PART 2: Topic Selector Tests
    # =========================================================================

    def test_topic_selector(self):
        """Test all topics in the selector"""
        print("\n" + "=" * 70)
        print("PART 2: TOPIC SELECTOR TESTS")
        print("=" * 70)

        self.click_tab('discovery')
        time.sleep(0.5)

        # Get category selector
        cat_select = Select(self.driver.find_element(By.ID, 'esc-category-select'))
        categories = [opt.get_attribute('value') for opt in cat_select.options if opt.get_attribute('value')]

        print(f"\n[2.1] Found {len(categories)} categories")
        self.log_test('topic_tests', f"Category count >= 15", len(categories) >= 15, f"{len(categories)} categories")

        # Test each category
        print("\n[2.2] Testing Category Filtering")
        all_topics = set()
        category_counts = {}

        for cat in categories:
            cat_select = Select(self.driver.find_element(By.ID, 'esc-category-select'))
            cat_select.select_by_value(cat)
            time.sleep(0.3)

            topic_select = Select(self.driver.find_element(By.ID, 'esc-topic-select'))
            topics = [opt.get_attribute('value') for opt in topic_select.options if opt.get_attribute('value')]
            category_counts[cat] = len(topics)
            all_topics.update(topics)

            self.log_test('topic_tests', f"Category '{cat[:20]}...' has topics", len(topics) > 0, f"{len(topics)} topics")

        # Reset to all categories
        cat_select = Select(self.driver.find_element(By.ID, 'esc-category-select'))
        cat_select.select_by_value('')
        time.sleep(0.3)

        topic_select = Select(self.driver.find_element(By.ID, 'esc-topic-select'))
        all_topic_options = [opt.get_attribute('value') for opt in topic_select.options if opt.get_attribute('value')]

        print(f"\n[2.3] Total Topics: {len(all_topic_options)}")
        self.log_test('topic_tests', f"Total topics >= 300", len(all_topic_options) >= 300, f"{len(all_topic_options)} topics")

        # Test loading specific topics
        print("\n[2.4] Testing Topic Loading")
        test_topics = ['hf-sglt2i', 'lipid-pcsk9i', 'cad-colchicine', 'af-doac', 'hf-arni']

        for topic_key in test_topics:
            try:
                topic_select = Select(self.driver.find_element(By.ID, 'esc-topic-select'))
                topic_select.select_by_value(topic_key)

                load_btn = self.driver.find_element(By.ID, 'btn-load-topic')
                self.click_element(load_btn)
                time.sleep(0.5)

                # Check if condition was populated
                condition = self.driver.find_element(By.ID, 'ctg-condition').get_attribute('value')
                intervention = self.driver.find_element(By.ID, 'ctg-intervention').get_attribute('value')

                self.log_test('topic_tests', f"Topic '{topic_key}' loads",
                             len(condition) > 0 and len(intervention) > 0,
                             f"Condition: {condition[:30]}...")
                self.topics_tested += 1
            except Exception as e:
                self.log_test('topic_tests', f"Topic '{topic_key}' loads", False, str(e)[:50])

        return all_topic_options

    # =========================================================================
    # PART 3: CT.gov Search Tests
    # =========================================================================

    def test_ctgov_search(self):
        """Test CT.gov API search functionality"""
        print("\n" + "=" * 70)
        print("PART 3: CT.GOV SEARCH TESTS")
        print("=" * 70)

        self.click_tab('discovery')
        time.sleep(0.5)

        # Test search with known parameters
        print("\n[3.1] Testing CT.gov API Search")

        test_searches = [
            # Note: Default filters are COMPLETED status, 100+ enrollment
            {'condition': 'Heart Failure', 'intervention': 'Dapagliflozin', 'expected_min': 1},
            {'condition': 'Atrial Fibrillation', 'intervention': 'Apixaban', 'expected_min': 1},
            {'condition': 'Coronary Artery Disease', 'intervention': 'Colchicine', 'expected_min': 1}
        ]

        for search in test_searches:
            try:
                # Clear status dropdown to avoid filter issues
                try:
                    status_select = Select(self.driver.find_element(By.ID, 'ctg-status'))
                    status_select.select_by_value('')  # Clear status filter
                except:
                    pass

                # Clear and fill inputs
                condition_input = self.driver.find_element(By.ID, 'ctg-condition')
                condition_input.clear()
                condition_input.send_keys(search['condition'])

                intervention_input = self.driver.find_element(By.ID, 'ctg-intervention')
                intervention_input.clear()
                intervention_input.send_keys(search['intervention'])

                # Click search
                search_btn = self.driver.find_element(By.ID, 'btn-search-ctgov')
                self.click_element(search_btn)

                # Wait for results with polling - longer timeout for proxy fallback
                max_wait = 45  # Increased to 45 seconds for proxy fallback attempts
                result_count = 0
                search_complete = False
                for i in range(max_wait):
                    time.sleep(1)
                    try:
                        status_elem = self.driver.find_element(By.ID, 'search-status')
                        status_text = status_elem.text
                        # Check if search is still in progress
                        if "Searching" in status_text or "Loading" in status_text:
                            continue
                        # Check if results are displayed
                        results_div = self.driver.find_element(By.ID, 'search-results')
                        if results_div.is_displayed():
                            search_complete = True
                            break
                        # Also break if error message appears
                        if "Error" in status_text or "No results" in status_text:
                            search_complete = True
                            break
                    except:
                        pass

                # Check results
                try:
                    count_elem = self.driver.find_element(By.ID, 'search-result-count')
                    count_text = count_elem.text
                    # Extract number from text like "(25 results)"
                    match = re.search(r'(\d+)', count_text)
                    if match:
                        result_count = int(match.group(1))
                except:
                    # Try counting table rows as fallback
                    try:
                        rows = self.driver.find_elements(By.CSS_SELECTOR, '#search-results-body tr')
                        result_count = len(rows)
                    except:
                        pass

                self.log_test('search_tests',
                             f"Search '{search['condition']}' + '{search['intervention']}'",
                             result_count >= search['expected_min'],
                             f"Found {result_count} trials")

                # Print browser logs if search failed
                if result_count == 0:
                    print("    Browser logs for failed search:")
                    self.print_browser_logs('[Fetch]')
                    self.print_browser_logs('[CT.gov]')

            except Exception as e:
                self.log_test('search_tests',
                             f"Search '{search['condition']}' + '{search['intervention']}'",
                             False, str(e)[:50])
                print("    Browser logs for exception:")
                self.print_browser_logs()

        # Test result selection
        print("\n[3.2] Testing Trial Selection")
        try:
            checkboxes = self.driver.find_elements(By.CSS_SELECTOR, '.trial-checkbox')
            if len(checkboxes) > 0:
                # Select first 3 trials
                for i, cb in enumerate(checkboxes[:3]):
                    self.click_element(cb)
                    time.sleep(0.2)

                self.log_test('search_tests', "Trial checkboxes work", True, f"Selected {min(3, len(checkboxes))} trials")
            else:
                self.log_test('search_tests', "Trial checkboxes work", False, "No checkboxes found")
        except Exception as e:
            self.log_test('search_tests', "Trial checkboxes work", False, str(e)[:50])

    # =========================================================================
    # PART 4: PubMed Cross-Validation Tests
    # =========================================================================

    def test_pubmed_validation(self):
        """Test PubMed search and cross-validation"""
        print("\n" + "=" * 70)
        print("PART 4: PUBMED CROSS-VALIDATION TESTS")
        print("=" * 70)

        self.click_tab('discovery')
        time.sleep(0.5)

        print("\n[4.1] Testing PubMed Search")

        test_queries = [
            {'query': 'DAPA-HF dapagliflozin heart failure', 'expected_min': 3},
            {'query': 'EMPEROR-Reduced empagliflozin', 'expected_min': 2},
            {'query': 'colchicine cardiovascular COLCOT', 'expected_min': 2}
        ]

        for test in test_queries:
            try:
                pubmed_input = self.driver.find_element(By.ID, 'pubmed-query')
                pubmed_input.clear()
                pubmed_input.send_keys(test['query'])

                # Find and click PubMed search button
                pubmed_btn = self.driver.find_element(By.ID, 'btn-search-pubmed')
                self.click_element(pubmed_btn)

                # Wait for results with longer timeout for proxy fallback
                max_wait = 45
                result_count = 0
                for i in range(max_wait):
                    time.sleep(1)
                    try:
                        status_elem = self.driver.find_element(By.ID, 'search-status')
                        status_text = status_elem.text
                        # Check if search is still in progress
                        if "Searching" in status_text or "Loading" in status_text:
                            continue
                        # Check if results are displayed
                        results_div = self.driver.find_element(By.ID, 'search-results')
                        if results_div.is_displayed():
                            break
                        if "Error" in status_text or "No results" in status_text:
                            break
                    except:
                        pass

                # Check for results - count table rows
                try:
                    rows = self.driver.find_elements(By.CSS_SELECTOR, '#search-results-body tr')
                    result_count = len(rows)
                except:
                    pass

                # Also check result count element
                if result_count == 0:
                    try:
                        count_elem = self.driver.find_element(By.ID, 'search-result-count')
                        count_text = count_elem.text
                        match = re.search(r'(\d+)', count_text)
                        if match:
                            result_count = int(match.group(1))
                    except:
                        pass

                has_results = result_count >= test['expected_min']
                self.log_test('search_tests', f"PubMed search: '{test['query'][:30]}...'",
                             has_results, f"Found {result_count} articles")

            except Exception as e:
                self.log_test('search_tests', f"PubMed search: '{test['query'][:30]}...'", False, str(e)[:50])

    # =========================================================================
    # PART 5: Full Pipeline Tests
    # =========================================================================

    def test_full_pipeline(self):
        """Test complete analysis pipeline end-to-end"""
        print("\n" + "=" * 70)
        print("PART 5: FULL PIPELINE TESTS")
        print("=" * 70)

        test_datasets = [
            {'name': 'SGLT2i', 'loader': 'btn-load-sglt2i', 'key': 'sglt2i'},
            {'name': 'PCSK9i', 'loader': 'btn-load-pcsk9i', 'key': 'pcsk9i'},
            {'name': 'Colchicine', 'loader': 'btn-load-colchicine', 'key': 'colchicine'}
        ]

        for dataset in test_datasets:
            print(f"\n[5.{test_datasets.index(dataset)+1}] Testing {dataset['name']} Pipeline")

            try:
                # Step 1: Load sample data
                self.click_tab('data')
                time.sleep(0.5)

                load_btn = self.driver.find_element(By.ID, dataset['loader'])
                self.click_element(load_btn)
                time.sleep(1)

                # Verify data loaded
                textarea = self.driver.find_element(By.ID, 'study-data')
                data = textarea.get_attribute('value')
                self.log_test('pipeline_tests', f"{dataset['name']}: Data loaded", len(data) > 50)

                # Step 2: Parse data
                parse_btn = self.driver.find_element(By.ID, 'btn-parse-data')
                self.click_element(parse_btn)
                time.sleep(1)

                # Check studies parsed
                study_count = self.driver.find_element(By.ID, 'study-count').text
                self.log_test('pipeline_tests', f"{dataset['name']}: Studies parsed", 'stud' in study_count.lower())

                # Step 3: Run meta-analysis
                self.click_tab('meta')
                time.sleep(0.5)

                # Select REML estimator
                try:
                    tau_select = Select(self.driver.find_element(By.ID, 'tau-estimator'))
                    tau_select.select_by_value('reml')
                except:
                    pass

                run_btn = self.driver.find_element(By.ID, 'btn-run-meta')
                self.click_element(run_btn)
                time.sleep(2)

                # Check results
                pooled = self.driver.find_element(By.ID, 'pooled-estimate').text
                ci = self.driver.find_element(By.ID, 'pooled-ci').text
                i2 = self.driver.find_element(By.ID, 'stat-i2').text

                self.log_test('pipeline_tests', f"{dataset['name']}: Pooled estimate",
                             pooled != '--' and '0.' in pooled, pooled)
                self.log_test('pipeline_tests', f"{dataset['name']}: 95% CI",
                             '0.' in ci, ci)
                self.log_test('pipeline_tests', f"{dataset['name']}: I-squared statistic",
                             '%' in i2, i2)

                # Step 4: Check forest plot
                forest_svg = self.driver.execute_script(
                    "return document.getElementById('forest-plot').outerHTML || '';"
                )
                self.log_test('pipeline_tests', f"{dataset['name']}: Forest plot",
                             '<svg' in forest_svg and len(forest_svg) > 200)

                # Step 5: Check funnel plot
                funnel_svg = self.driver.execute_script(
                    "return document.getElementById('funnel-plot').outerHTML || '';"
                )
                self.log_test('pipeline_tests', f"{dataset['name']}: Funnel plot",
                             '<svg' in funnel_svg and 'circle' in funnel_svg)

                # Step 6: GRADE assessment
                self.click_tab('grade')
                time.sleep(0.5)

                grade_btn = self.driver.find_element(By.ID, 'btn-calculate-grade')
                self.click_element(grade_btn)
                time.sleep(1)

                grade_result = self.driver.find_element(By.ID, 'grade-result-badge').text
                self.log_test('pipeline_tests', f"{dataset['name']}: GRADE calculated",
                             grade_result in ['HIGH', 'MODERATE', 'LOW', 'VERY LOW'], grade_result)

                # Step 7: Recommendation
                self.click_tab('recommendation')
                time.sleep(0.5)

                rec_btn = self.driver.find_element(By.ID, 'btn-derive-recommendation')
                self.click_element(rec_btn)
                time.sleep(1)

                rec_class = self.driver.find_element(By.ID, 'rec-class').text
                rec_level = self.driver.find_element(By.ID, 'rec-level').text
                self.log_test('pipeline_tests', f"{dataset['name']}: ESC Recommendation",
                             rec_class in ['I', 'IIa', 'IIb', 'III'] and rec_level in ['A', 'B', 'C'],
                             f"Class {rec_class}, Level {rec_level}")

                # Step 8: Summary of Findings
                self.click_tab('sof')
                time.sleep(0.5)

                sof_btn = self.driver.find_element(By.ID, 'btn-generate-sof')
                self.click_element(sof_btn)
                time.sleep(1)

                sof_body = self.driver.find_element(By.ID, 'sof-body')
                sof_html = sof_body.get_attribute('innerHTML')
                self.log_test('pipeline_tests', f"{dataset['name']}: SoF table",
                             '<tr' in sof_html or len(sof_html) > 50)

            except Exception as e:
                self.log_test('pipeline_tests', f"{dataset['name']}: Pipeline execution", False, str(e)[:80])

    # =========================================================================
    # PART 6: Validation Against Published Meta-Analyses
    # =========================================================================

    def test_validation_against_published(self):
        """Validate results against published meta-analyses"""
        print("\n" + "=" * 70)
        print("PART 6: VALIDATION AGAINST PUBLISHED META-ANALYSES")
        print("=" * 70)

        # Topics with sample data buttons in web tool (4+ RCTs only)
        # SGLT2i: 5 RCTs, Colchicine: 4 RCTs
        # Note: PCSK9i excluded (only 2 RCTs)
        topics_with_sample_data = {
            'sglt2i': 'btn-load-sglt2i',
            'colchicine': 'btn-load-colchicine'
        }

        validation_count = 0
        for key, ref in self.VALIDATION_DATA.items():
            # Only validate topics that have sample data buttons
            if key not in topics_with_sample_data:
                continue

            validation_count += 1
            print(f"\n[6.{validation_count}] Validating {ref['name']}")
            print(f"    Reference: {ref['reference']}")
            print(f"    Guideline: {ref.get('guideline', 'N/A')}")

            try:
                # Load data
                self.click_tab('data')
                time.sleep(0.5)

                loader_id = topics_with_sample_data[key]
                load_btn = self.driver.find_element(By.ID, loader_id)
                self.click_element(load_btn)
                time.sleep(1)

                # Run meta-analysis
                self.click_tab('meta')
                time.sleep(0.5)

                run_btn = self.driver.find_element(By.ID, 'btn-run-meta')
                self.click_element(run_btn)
                time.sleep(2)

                # Get results
                pooled_text = self.driver.find_element(By.ID, 'pooled-estimate').text
                ci_text = self.driver.find_element(By.ID, 'pooled-ci').text
                i2_text = self.driver.find_element(By.ID, 'stat-i2').text

                # Parse values
                pooled_val = float(pooled_text) if pooled_text and pooled_text != '--' else None

                ci_match = re.search(r'(\d+\.?\d*)\s*(?:[-–]|to)\s*(\d+\.?\d*)', ci_text)
                ci_low = float(ci_match.group(1)) if ci_match else None
                ci_high = float(ci_match.group(2)) if ci_match else None

                i2_match = re.search(r'(\d+\.?\d*)%?', i2_text)
                i2_val = float(i2_match.group(1)) if i2_match else None

                # Get expected value (HR, OR, or RR)
                expected_val = ref.get('expected_hr') or ref.get('expected_or') or ref.get('expected_rr')
                effect_type = 'HR' if 'expected_hr' in ref else ('OR' if 'expected_or' in ref else 'RR')

                # Validate
                if pooled_val and expected_val:
                    val_diff = abs(pooled_val - expected_val)
                    val_match = val_diff <= ref['tolerance']
                    self.log_test('validation_tests',
                                 f"{key}: {effect_type} matches ({pooled_val:.2f} vs {expected_val:.2f})",
                                 val_match, f"Diff: {val_diff:.3f}")
                else:
                    self.log_test('validation_tests', f"{key}: {effect_type} matches", False, "Could not parse value")

                if ci_low and ci_high:
                    ci_low_diff = abs(ci_low - ref['expected_ci_low'])
                    ci_high_diff = abs(ci_high - ref['expected_ci_high'])
                    ci_ok = ci_low_diff <= ref['tolerance'] and ci_high_diff <= ref['tolerance']
                    self.log_test('validation_tests',
                                 f"{key}: CI matches ({ci_low:.2f}-{ci_high:.2f} vs {ref['expected_ci_low']:.2f}-{ref['expected_ci_high']:.2f})",
                                 ci_ok, f"Diff: {ci_low_diff:.3f}, {ci_high_diff:.3f}")
                else:
                    self.log_test('validation_tests', f"{key}: CI matches", False, "Could not parse CI")

                # Calculate concordance percentage
                if pooled_val and expected_val and ci_low and ci_high:
                    val_concordance = 100 * (1 - val_diff / expected_val)
                    ci_concordance = 100 * (1 - (ci_low_diff + ci_high_diff) / 2 / 0.1)  # Normalized
                    overall = (val_concordance + ci_concordance) / 2
                    self.log_test('validation_tests', f"{key}: Concordance >= 95%",
                                 overall >= 95, f"{overall:.1f}%")

            except Exception as e:
                self.log_test('validation_tests', f"{key}: Validation", False, str(e)[:80])

        # Print summary of all ESC validation topics (documentation)
        print(f"\n    ESC VALIDATION DATA SUMMARY:")
        print(f"    Topics documented: {len(self.VALIDATION_DATA)}")
        print(f"    Topics with sample data tested: {validation_count}")
        print(f"    Topics requiring sample data buttons: {len(self.VALIDATION_DATA) - validation_count}")

        # Run built-in validation
        print("\n[6.4] Running Built-in Validation")
        try:
            self.click_tab('validation')
            time.sleep(0.5)

            val_btn = self.driver.find_element(By.ID, 'btn-run-validation')
            self.click_element(val_btn)
            time.sleep(2)

            val_results = self.driver.find_element(By.ID, 'validation-results')
            val_html = val_results.get_attribute('innerHTML')

            has_comparison = 'Vaduganathan' in val_html or 'Published' in val_html
            has_score = '%' in val_html or 'EXACT' in val_html or 'MATCH' in val_html

            self.log_test('validation_tests', "Built-in validation runs", has_comparison and has_score)

        except Exception as e:
            self.log_test('validation_tests', "Built-in validation runs", False, str(e)[:50])

    # =========================================================================
    # PART 7: Batch Topic Testing
    # =========================================================================

    def test_batch_topics(self, sample_size=20):
        """Test a batch of topics for search functionality"""
        print("\n" + "=" * 70)
        print(f"PART 7: BATCH TOPIC TESTING ({sample_size} topics)")
        print("=" * 70)

        self.click_tab('discovery')
        time.sleep(0.5)

        # Get all topics
        cat_select = Select(self.driver.find_element(By.ID, 'esc-category-select'))
        cat_select.select_by_value('')
        time.sleep(0.3)

        topic_select = Select(self.driver.find_element(By.ID, 'esc-topic-select'))
        all_topics = [opt.get_attribute('value') for opt in topic_select.options if opt.get_attribute('value')]

        # Sample topics evenly
        import random
        if len(all_topics) > sample_size:
            step = len(all_topics) // sample_size
            test_topics = [all_topics[i * step] for i in range(sample_size)]
        else:
            test_topics = all_topics

        print(f"\nTesting {len(test_topics)} topics from {len(all_topics)} total")

        successful_loads = 0
        successful_searches = 0

        for i, topic_key in enumerate(test_topics):
            try:
                # Select topic
                topic_select = Select(self.driver.find_element(By.ID, 'esc-topic-select'))
                topic_select.select_by_value(topic_key)

                # Load topic
                load_btn = self.driver.find_element(By.ID, 'btn-load-topic')
                self.click_element(load_btn)
                time.sleep(0.3)

                # Check if loaded
                condition = self.driver.find_element(By.ID, 'ctg-condition').get_attribute('value')
                if len(condition) > 0:
                    successful_loads += 1

                self.topics_tested += 1

                # Print progress every 5 topics
                if (i + 1) % 5 == 0:
                    print(f"  Tested {i+1}/{len(test_topics)} topics - {successful_loads} loaded successfully")

            except Exception as e:
                continue

        load_rate = 100 * successful_loads / len(test_topics) if test_topics else 0
        self.log_test('topic_tests', f"Batch topic load rate >= 90%", load_rate >= 90, f"{load_rate:.1f}%")

        print(f"\n  Summary: {successful_loads}/{len(test_topics)} topics loaded successfully ({load_rate:.1f}%)")

    # =========================================================================
    # PART 8: NMA and Subgroup Tests
    # =========================================================================

    def test_advanced_features(self):
        """Test NMA and Subgroup analysis"""
        print("\n" + "=" * 70)
        print("PART 8: ADVANCED FEATURES (NMA, Subgroups)")
        print("=" * 70)

        # Test NMA
        print("\n[8.1] Network Meta-Analysis")
        try:
            self.click_tab('nma')
            time.sleep(0.5)

            # Load sample NMA data
            load_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Load Sample')]")
            self.click_element(load_btn)
            time.sleep(1)

            # Run NMA
            run_btn = self.driver.find_element(By.ID, 'btn-run-nma')
            self.click_element(run_btn)
            time.sleep(2)

            # Check SUCRA
            sucra_body = self.driver.find_element(By.ID, 'sucra-body')
            sucra_rows = sucra_body.find_elements(By.TAG_NAME, 'tr')
            self.log_test('pipeline_tests', "NMA SUCRA rankings", len(sucra_rows) > 1, f"{len(sucra_rows)} treatments")

            # Check network diagram
            network_svg = self.driver.find_element(By.ID, 'network-svg')
            svg_html = network_svg.get_attribute('outerHTML')
            self.log_test('pipeline_tests', "NMA network diagram", 'circle' in svg_html and 'line' in svg_html)

            # Check league table
            league = self.driver.find_element(By.ID, 'league-table-container')
            self.log_test('pipeline_tests', "NMA league table", '<table' in league.get_attribute('innerHTML'))

        except Exception as e:
            self.log_test('pipeline_tests', "NMA execution", False, str(e)[:50])

        # Test Subgroup Analysis
        print("\n[8.2] Subgroup Analysis")
        try:
            self.click_tab('subgroups')
            time.sleep(0.5)

            # Enter subgroup data
            var_input = self.driver.find_element(By.ID, 'subgroup-variable')
            var_input.clear()
            var_input.send_keys('Diabetes Status')

            data_input = self.driver.find_element(By.ID, 'subgroup-data')
            data_input.clear()
            data_input.send_keys('Diabetes Yes, 0.76, 0.68, 0.85, 8000\nDiabetes No, 0.79, 0.71, 0.88, 14000')

            # Run analysis
            run_btn = self.driver.find_element(By.ID, 'btn-run-subgroup')
            self.click_element(run_btn)
            time.sleep(1)

            # Check results
            results = self.driver.find_element(By.ID, 'subgroup-results')
            self.log_test('pipeline_tests', "Subgroup analysis results", '<table' in results.get_attribute('innerHTML'))

            # Check ICEMAN
            iceman_score = self.driver.find_element(By.ID, 'iceman-score').text
            iceman_rating = self.driver.find_element(By.ID, 'iceman-rating').text
            self.log_test('pipeline_tests', "ICEMAN credibility",
                         iceman_score != '--' and iceman_rating in ['High', 'Moderate', 'Low'],
                         f"{iceman_rating} ({iceman_score})")

        except Exception as e:
            self.log_test('pipeline_tests', "Subgroup analysis", False, str(e)[:50])

    # =========================================================================
    # Main Test Runner
    # =========================================================================

    def run_all_tests(self):
        """Run complete test suite"""
        try:
            self.setup()

            # Run all test sections
            self.test_ui_elements()
            all_topics = self.test_topic_selector()
            self.test_ctgov_search()
            self.test_pubmed_validation()
            self.test_full_pipeline()
            self.test_validation_against_published()
            self.test_batch_topics(sample_size=30)  # Test 30 random topics
            self.test_advanced_features()

        except Exception as e:
            print(f"\n[FATAL ERROR]: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.print_summary()

    def print_summary(self):
        """Print comprehensive test summary"""
        elapsed = time.time() - self.start_time if self.start_time else 0

        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)

        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0

        print(f"""
  Duration: {elapsed:.1f} seconds

  OVERALL RESULTS:
  ----------------
  Total Tests: {total}
  Passed: {self.passed}
  Failed: {self.failed}
  Pass Rate: {pass_rate:.1f}%
  Topics Tested: {self.topics_tested}

  BY CATEGORY:
  ------------""")

        for category, tests in self.results.items():
            cat_passed = sum(1 for t in tests if t['passed'])
            cat_total = len(tests)
            cat_rate = (cat_passed / cat_total * 100) if cat_total > 0 else 0
            print(f"  {category}: {cat_passed}/{cat_total} ({cat_rate:.1f}%)")

        if self.failed > 0:
            print("\n  FAILED TESTS:")
            print("  -------------")
            for category, tests in self.results.items():
                for t in tests:
                    if not t['passed']:
                        print(f"    [{category}] {t['test']}: {t['details'][:60]}")

        # Validation summary
        print("\n  VALIDATION SUMMARY:")
        print("  -------------------")
        val_tests = self.results.get('validation_tests', [])
        for t in val_tests:
            status = "[OK]" if t['passed'] else "[X]"
            print(f"    {status} {t['test']}")

        print("\n" + "=" * 70)

        # Keep browser open
        print("\nBrowser will remain open for 60 seconds for inspection...")
        print("Press Ctrl+C to close earlier.")
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            pass
        finally:
            self.driver.quit()

        # Save results
        results_file = r"C:\Users\user\Downloads\lec_phase0_project\full_pipeline_test_results.json"
        with open(results_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'duration_seconds': elapsed,
                'total_tests': total,
                'passed': self.passed,
                'failed': self.failed,
                'pass_rate': pass_rate,
                'topics_tested': self.topics_tested,
                'results': self.results
            }, f, indent=2)
        print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    tester = LECFullPipelineTester()
    tester.run_all_tests()
