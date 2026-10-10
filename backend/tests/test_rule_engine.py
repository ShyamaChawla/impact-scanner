from app.rule_engine import evaluate_rule

def test_basic_pass_fail():
    rule = {"id":"QTY", "logic":{">":[{"var":"Quantity"},0]}, "impact":"Quantity must be positive."}
    assert evaluate_rule(rule, {"Quantity": 2})["status"] == "PASS"
    assert evaluate_rule(rule, {"Quantity": 0})["status"] == "FAIL"

def test_applicability_skips_out_of_scope():
    rule = {"id":"ISIN", "applies_when":{"==":[{"var":"Asset_Class"},"Derivative"]},
            "logic":{"var":"Underlying_ISIN"}}
    assert evaluate_rule(rule, {"Asset_Class":"Equity"})["status"] == "SKIP"

def test_bad_regex_is_error():
    rule = {"id":"REGEX", "logic":{"regex":[{"var":"Code"},"["]}}
    assert evaluate_rule(rule, {"Code":"abc"})["status"] == "ERROR"

def test_unsupported_operator_is_error():
    rule = {"id":"X", "logic":{"eval":["danger"]}}
    assert evaluate_rule(rule, {})["status"] == "ERROR"
