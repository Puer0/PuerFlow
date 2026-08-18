package auth

import "testing"

func TestExtractBearerToken(t *testing.T) {
	cases := []struct {
		name    string
		header  string
		want    string
		wantErr bool
	}{
		{name: "Bearer", header: "Bearer abc", want: "abc"},
		{name: "bearer lower", header: "bearer abc", want: "abc"},
		{name: "BEARER upper", header: "BEARER abc", want: "abc"},
		{name: "trim spaces", header: "  Bearer abc  ", want: "abc"},
		{name: "missing space", header: "Bearerabc", wantErr: true},
		{name: "missing token", header: "Bearer ", wantErr: true},
		{name: "empty", header: "", wantErr: true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := ExtractBearerToken(tc.header)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("expected error, got token %q", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != tc.want {
				t.Fatalf("got %q, want %q", got, tc.want)
			}
		})
	}
}
