package org.fantasytv.overlay;

import org.junit.Test;
import static org.junit.Assert.*;

public class EndpointPolicyTest {
    @Test public void validHttpsWithoutSecrets() {
        assertEquals("scores.example",EndpointPolicy.validate("https://scores.example/api/scores").getHost());
        String token = "aBcdEFghIJklMNopQRstUVwxYZ0123_-";
        assertEquals(token,EndpointPolicy.token(token));
    }
    @Test public void insecureOrCredentialLinksAreRejected() {
        for (String link : new String[]{"http://scores.example/api/scores","https://user:pass@scores.example/x",
            "https://scores.example/x?token=secret","https://scores.example/x#secret","file:///tmp/feed.json","https:///x",
            "https://scores.example:0/x","https://scores.example:99999/x","https://scores.example/x\r\nBad: header"}) {
            try { EndpointPolicy.validate(link); fail("Accepted invalid URL"); } catch (IllegalArgumentException expected) { }
        }
    }
    @Test public void headerInjectionAndLongTokensAreRejected() {
        for (String value : new String[]{"x\r\nBad: header","abc def","short-token","x\tkey","x\u0000key",String.join("",java.util.Collections.nCopies(4097,"a"))}) {
            try { EndpointPolicy.token(value); fail("Accepted invalid token"); } catch (IllegalArgumentException expected) { }
        }
    }
}
