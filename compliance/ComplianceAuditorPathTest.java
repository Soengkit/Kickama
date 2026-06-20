package com.tentoftrials.compliance;

import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public class ComplianceAuditorPathTest {
    public static void main(String[] args) {
        ComplianceAuditor auditor = new ComplianceAuditor("https://regulator.invalid", "test", "test");

        assertCompliant(
            auditor.auditCompliance("PATH_POLICY", policy("reports/daily/2026-06-20.csv")),
            "POSIX path should match POSIX include rule"
        );
        assertCompliant(
            auditor.auditCompliance("PATH_POLICY", policy("reports\\daily\\2026-06-20.csv")),
            "Windows path should match the same POSIX include rule"
        );
        assertCompliant(
            auditor.auditCompliance("PATH_POLICY", ignoredPolicy("reports\\daily\\scratch\\debug.log")),
            "Windows path should match POSIX ignore rule before include enforcement"
        );
        assertCompliant(
            auditor.auditCompliance("FILE_PATH_POLICY", globPolicy("exports\\compliance\\audit.csv")),
            "Windows path should match slash-agnostic glob include rule"
        );
        assertViolationContains(
            auditor.auditCompliance("PATH_POLICY", policy("reports\\monthly\\2026-06.csv")),
            "reports\\monthly\\2026-06.csv"
        );
    }

    private static Map<String, Object> policy(String path) {
        Map<String, Object> data = new HashMap<>();
        data.put("path", path);
        data.put("include_paths", Arrays.asList("reports/daily"));
        data.put("ignore_paths", Arrays.asList("reports/daily/scratch"));
        return data;
    }

    private static Map<String, Object> ignoredPolicy(String path) {
        Map<String, Object> data = policy(path);
        data.put("ignore_paths", Arrays.asList("reports/daily/scratch"));
        return data;
    }

    private static Map<String, Object> globPolicy(String path) {
        Map<String, Object> data = new HashMap<>();
        data.put("path", path);
        data.put("include_paths", Arrays.asList("exports/**"));
        return data;
    }

    private static void assertCompliant(ComplianceAuditor.ComplianceResult result, String message) {
        if (!result.isCompliant()) {
            throw new AssertionError(message + ": " + result.getSummary());
        }
    }

    private static void assertViolationContains(ComplianceAuditor.ComplianceResult result, String expected) {
        if (result.isCompliant()) {
            throw new AssertionError("Expected path policy violation, got success");
        }
        boolean found = false;
        for (String violation : result.getViolations()) {
            if (violation.contains(expected)) {
                found = true;
                break;
            }
        }
        if (!found) {
            throw new AssertionError("Expected violation to include original path: " + expected);
        }
    }
}
