package dev.finrag.gateway.provider;

import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientResponseException;

/** An upstream failure. {@code retryable} is true for timeouts, I/O errors, 429 and 5xx. */
public class ProviderException extends RuntimeException {

    private final String provider;
    private final boolean retryable;

    public ProviderException(String provider, String message, boolean retryable, Throwable cause) {
        super(provider + ": " + message, cause);
        this.provider = provider;
        this.retryable = retryable;
    }

    public String provider() {
        return provider;
    }

    public boolean retryable() {
        return retryable;
    }

    /** Wrap a RestClient failure, without echoing the upstream response body (it may contain prompt text). */
    public static ProviderException from(String provider, RuntimeException e) {
        if (e instanceof RestClientResponseException r) {
            int status = r.getStatusCode().value();
            return new ProviderException(provider, "upstream HTTP " + status, status == 429 || status >= 500, e);
        }
        if (e instanceof ResourceAccessException) {
            return new ProviderException(provider, "upstream unreachable or timed out", true, e);
        }
        return new ProviderException(provider, e.getClass().getSimpleName(), false, e);
    }
}
