package dev.finrag.gateway.security;

import ch.qos.logback.classic.pattern.MessageConverter;
import ch.qos.logback.classic.spi.ILoggingEvent;

/**
 * Logback converter used in place of %msg (see logback-spring.xml), so every log line from any
 * library passes through the Redactor before it is written.
 */
public class RedactingMessageConverter extends MessageConverter {

    @Override
    public String convert(ILoggingEvent event) {
        return Redactor.redact(super.convert(event));
    }
}
