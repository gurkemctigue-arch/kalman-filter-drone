"""Bind the five actual Linux platform skips to test IDs and frozen decorators."""
import ast
import re

EXPECTED_FULL_SUITE_SKIPS = 5
EXPECTED_SKIPS = {
    'test_document_runtime_preparation.DocumentRuntimePreparationTests.test_word_script_paths_only_never_starts_word_and_preserves_existing_pdf':
        ('tests/test_document_runtime_preparation.py', 'shutil.which("powershell")', 'Windows PowerShell path-only fixture'),
    'test_reliability_v4_report.ReliabilityReportTests.test_node_gate_verifies_python_sources_without_rendering_docx':
        ('tests/test_reliability_v4_report.py', 'NODE_DOCX_AVAILABLE', 'Node.js and npm docx are required for the source-only renderer gate'),
    'test_project_progress_monitor.ProjectProgressTests.test_real_windows_reader_releasing_lock_allows_json_and_html_publication':
        ('tests/test_project_progress_monitor.py', 'os.name == "nt"', 'Real Windows sharing semantics'),
    'test_project_progress_monitor.ProjectProgressTests.test_real_windows_persistent_lock_preserves_snapshot_and_cleans_temporary':
        ('tests/test_project_progress_monitor.py', 'os.name == "nt"', 'Real Windows sharing semantics'),
    'test_project_progress_monitor.ProjectProgressTests.test_real_monitor_survives_busy_snapshot_without_restarting_or_killing_target':
        ('tests/test_project_progress_monitor.py', 'os.name == "nt"', 'Real Windows sharing semantics'),
}
SKIP_SOURCE_PATHS = tuple(sorted({row[0] for row in EXPECTED_SKIPS.values()}))


def expression(value):
    return ast.dump(ast.parse(value, mode='eval').body, include_attributes=False)


def validate_skip_sources(sources):
    """Parse source only; importing test modules could execute tool checks."""
    if set(sources) != set(SKIP_SOURCE_PATHS):
        raise ValueError('Incomplete frozen platform skip source set')
    observed = {}
    for path, text in sources.items():
        module = path.rsplit('/', 1)[-1].removesuffix('.py')
        for cls in ast.parse(text, filename=path).body:
            if not isinstance(cls, ast.ClassDef):
                continue
            for method in cls.body:
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in method.decorator_list:
                    if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                            and isinstance(decorator.func.value, ast.Name)
                            and decorator.func.value.id == 'unittest'
                            and decorator.func.attr.startswith('skip')):
                        test_id = module + '.' + cls.name + '.' + method.name
                        if (decorator.func.attr != 'skipUnless' or len(decorator.args) != 2
                                or decorator.keywords or test_id in observed
                                or not isinstance(decorator.args[1], ast.Constant)
                                or not isinstance(decorator.args[1].value, str)):
                            raise ValueError('Unregistered or malformed platform skip decorator: ' + test_id)
                        observed[test_id] = (path, ast.dump(decorator.args[0], include_attributes=False),
                                             decorator.args[1].value)
    expected = {name: (row[0], expression(row[1]), row[2]) for name, row in EXPECTED_SKIPS.items()}
    if observed != expected:
        raise ValueError('Frozen platform skip identities, predicates, reasons or counts differ')
    return {'expected_skip_count': EXPECTED_FULL_SUITE_SKIPS,
            'source_counts': {path: sum(row[0] == path for row in EXPECTED_SKIPS.values()) for path in SKIP_SOURCE_PATHS},
            'expected_tests': {name: row[2] for name, row in EXPECTED_SKIPS.items()}}


def validate_observed_skips(log_text):
    """Accept Python unittest verbose ID formats with or without method suffix."""
    observed = {}
    for line in log_text.splitlines():
        match = re.fullmatch(r'(test\S+) \(([^)]+)\) \.\.\. skipped (.+)', line)
        if not match:
            if ' ... skipped ' in line:
                raise ValueError('Unparseable actual unittest skip identity')
            continue
        method, qualifier, quoted_reason = match.groups()
        test_id = qualifier if qualifier.endswith('.' + method) else qualifier + '.' + method
        try:
            reason = ast.literal_eval(quoted_reason)
        except (ValueError, SyntaxError) as error:
            raise ValueError('Unparseable actual unittest skip reason') from error
        if not isinstance(reason, str) or test_id in observed:
            raise ValueError('Duplicate or invalid actual unittest skip identity')
        observed[test_id] = reason
    if observed != {name: row[2] for name, row in EXPECTED_SKIPS.items()}:
        raise ValueError('Actual skipped tests differ from the five frozen Linux platform skips')
    return observed
