package daemon

import "testing"

func TestDispatchMaxLen_Sufficient(t *testing.T) {
	if dispatchMaxLen < 10000 {
		t.Errorf("dispatchMaxLen = %d, want >= 10000 to prevent event loss at scale", dispatchMaxLen)
	}
}
