package dev.finrag.gateway.api;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import dev.finrag.gateway.api.Dtos.ErrorBody;
import dev.finrag.gateway.provider.ProviderException;
import dev.finrag.gateway.routing.RoutingException;
import dev.finrag.gateway.web.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;

/** Maps failures to JSON errors that carry the request ID, never upstream bodies or stack traces. */
@RestControllerAdvice
public class ErrorHandler {

    private static final Logger log = LoggerFactory.getLogger(ErrorHandler.class);

    @ExceptionHandler(RoutingException.class)
    ResponseEntity<ErrorBody> routing(RoutingException e, HttpServletRequest req) {
        HttpStatus status = switch (e.reason()) {
            case UNKNOWN_MODEL -> HttpStatus.NOT_FOUND;
            case WRONG_KIND -> HttpStatus.BAD_REQUEST;
            case PROVIDER_DISABLED -> HttpStatus.SERVICE_UNAVAILABLE;
        };
        return body(status, "routing_error", e.getMessage(), req);
    }

    @ExceptionHandler(ProviderException.class)
    ResponseEntity<ErrorBody> provider(ProviderException e, HttpServletRequest req) {
        log.warn("provider failure: {}", e.getMessage());
        return body(HttpStatus.BAD_GATEWAY, "provider_error", e.getMessage(), req);
    }

    @ExceptionHandler({ MethodArgumentNotValidException.class, HttpMessageNotReadableException.class })
    ResponseEntity<ErrorBody> invalid(Exception e, HttpServletRequest req) {
        return body(HttpStatus.BAD_REQUEST, "invalid_request", "request body failed validation", req);
    }

    private static ResponseEntity<ErrorBody> body(HttpStatus status, String type, String message, HttpServletRequest req) {
        return ResponseEntity.status(status).body(new ErrorBody(RequestIdFilter.of(req), type, message));
    }
}
