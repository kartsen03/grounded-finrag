package dev.finrag.gateway.routing;

public class RoutingException extends RuntimeException {

    public enum Reason {
        UNKNOWN_MODEL, WRONG_KIND, PROVIDER_DISABLED
    }

    private final Reason reason;

    public RoutingException(Reason reason, String message) {
        super(message);
        this.reason = reason;
    }

    public Reason reason() {
        return reason;
    }
}
