package dev.finrag.gateway.security;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Masks secrets and personal data before text reaches a log line or the audit log.
 * Patterns are deliberately broad: a false positive costs a masked token, a false negative
 * leaks a credential or a customer's data into log storage that many people can read.
 */
public final class Redactor {

    private record Rule(String label, Pattern pattern) {
    }

    private static final List<Rule> RULES = List.of(
            new Rule("PRIVATE_KEY", Pattern.compile("-----BEGIN [A-Z ]*PRIVATE KEY-----[\\s\\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
            new Rule("AWS_ACCESS_KEY", Pattern.compile("\\b(?:AKIA|ASIA)[0-9A-Z]{16}\\b")),
            new Rule("API_KEY", Pattern.compile("\\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}\\b")),
            new Rule("GITHUB_TOKEN", Pattern.compile("\\bgh[pousr]_[A-Za-z0-9]{30,}\\b")),
            new Rule("JWT", Pattern.compile("\\beyJ[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,}\\b")),
            new Rule("BEARER", Pattern.compile("(?i)\\bbearer\\s+[A-Za-z0-9._~+/=-]{8,}")),
            new Rule("SECRET_ASSIGNMENT",
                    Pattern.compile("(?i)\\b(password|passwd|secret|api[_-]?key|token)\\s*[:=]\\s*\\S+")),
            new Rule("EMAIL", Pattern.compile("\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b")),
            new Rule("SSN", Pattern.compile("\\b\\d{3}-\\d{2}-\\d{4}\\b")),
            new Rule("PHONE", Pattern.compile("(?<!\\d)(?:\\+1[ .-]?)?\\(?\\d{3}\\)?[ .-]\\d{3}[ .-]\\d{4}(?!\\d)")));

    private static final Pattern CARD_CANDIDATE = Pattern.compile("(?<!\\d)(?:\\d[ -]?){13,19}(?!\\d)");

    private Redactor() {
    }

    public static String redact(String text) {
        if (text == null || text.isEmpty()) {
            return text;
        }
        String out = text;
        for (Rule rule : RULES) {
            out = rule.pattern().matcher(out).replaceAll("[REDACTED_" + rule.label() + "]");
        }
        return redactCards(out);
    }

    /** Card numbers only when the Luhn checksum passes, so ordinary long figures survive. */
    private static String redactCards(String text) {
        Matcher m = CARD_CANDIDATE.matcher(text);
        StringBuilder sb = new StringBuilder();
        while (m.find()) {
            String digits = m.group().replaceAll("[ -]", "");
            m.appendReplacement(sb, digits.length() >= 13 && luhn(digits) ? "[REDACTED_CARD]"
                    : Matcher.quoteReplacement(m.group()));
        }
        m.appendTail(sb);
        return sb.toString();
    }

    static boolean luhn(String digits) {
        int sum = 0;
        boolean twice = false;
        for (int i = digits.length() - 1; i >= 0; i--) {
            int d = digits.charAt(i) - '0';
            if (twice) {
                d *= 2;
                if (d > 9) {
                    d -= 9;
                }
            }
            sum += d;
            twice = !twice;
        }
        return sum % 10 == 0;
    }
}
