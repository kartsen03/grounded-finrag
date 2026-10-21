package dev.finrag.gateway.security;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class RedactorTests {

    @Test
    void masksSecrets() {
        String out = Redactor.redact("key sk-abcdefghijklmnop1234 aws AKIAABCDEFGHIJKLMNOP auth Bearer abc.def.ghi123 "
                + "password=hunter2 gh ghp_abcdefghijklmnopqrstuvwxyz0123456789");
        assertThat(out).doesNotContain("sk-abcdefghijklmnop1234", "AKIAABCDEFGHIJKLMNOP", "abc.def.ghi123",
                "hunter2", "ghp_abcdefghijklmnopqrstuvwxyz0123456789");
        assertThat(out).contains("[REDACTED_API_KEY]", "[REDACTED_AWS_ACCESS_KEY]", "[REDACTED_BEARER]");
    }

    @Test
    void masksPersonalData() {
        String out = Redactor.redact("Contact jane.doe@example.com or (617) 555-0182, SSN 123-45-6789, "
                + "card 4111 1111 1111 1111");
        assertThat(out).doesNotContain("jane.doe@example.com", "555-0182", "123-45-6789", "4111 1111 1111 1111");
        assertThat(out).contains("[REDACTED_EMAIL]", "[REDACTED_PHONE]", "[REDACTED_SSN]", "[REDACTED_CARD]");
    }

    @Test
    void keepsFinancialFiguresThatAreNotCards() {
        // A long figure that fails the Luhn check, and ordinary statement numbers, survive.
        String text = "Total assets 1234567890123 and revenue of $23,601 million in FY2022";
        assertThat(Redactor.redact(text)).isEqualTo(text);
        assertThat(Redactor.luhn("4111111111111111")).isTrue();
        assertThat(Redactor.luhn("1234567890123")).isFalse();
    }
}
