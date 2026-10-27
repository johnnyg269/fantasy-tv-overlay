package org.fantasytv.overlay;

import java.net.URI;
import java.net.URISyntaxException;

/** Credentials belong in the Authorization header, never in a link. */
public final class EndpointPolicy {
    private EndpointPolicy() {}
    public static URI validate(String input) {
        if (input == null || input.length() > 2048) throw new IllegalArgumentException("Enter a valid HTTPS feed URL");
        try {
            URI uri = new URI(input.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null || uri.getHost().isEmpty()
                || uri.getRawUserInfo() != null || uri.getRawFragment() != null || uri.getRawQuery() != null
                || uri.getPort() == 0 || uri.getPort() < -1 || uri.getPort() > 65535) {
                throw new IllegalArgumentException("Use HTTPS without credentials, a query string, or a fragment");
            }
            return uri;
        } catch (URISyntaxException e) {
            throw new IllegalArgumentException("Enter a valid HTTPS feed URL");
        }
    }
    public static String token(String value) {
        if (value == null || value.isEmpty()) return "";
        if (!value.matches("[A-Za-z0-9_-]{32,256}")) {
            throw new IllegalArgumentException("Feed token must be 32–256 URL-safe characters");
        }
        return value;
    }
}
