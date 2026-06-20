package orderbook

import (
	"strings"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/tent-of-trials/market/types"
)

func dec(value string) decimal.Decimal {
	return decimal.RequireFromString(value)
}

func TestReplayDeltasPassesMatchingFixture(t *testing.T) {
	mismatch, err := ReplayDeltas(types.Symbol("BTC-USD"), []ReplayDelta{
		{Symbol: "BTC-USD", Side: DeltaBid, Price: dec("100"), Size: dec("1.5"), Expected: 1},
		{Symbol: "BTC-USD", Side: DeltaBid, Price: dec("101"), Size: dec("2.0"), Expected: 2},
		{Symbol: "BTC-USD", Side: DeltaAsk, Price: dec("102"), Size: dec("0.5"), Expected: 1},
	})
	if err != nil {
		t.Fatalf("ReplayDeltas returned error: %v", err)
	}
	if mismatch != nil {
		t.Fatalf("expected no mismatch, got %s", mismatch.Summary())
	}
}

func TestReplayDeltasReportsFirstDivergentStep(t *testing.T) {
	mismatch, err := ReplayDeltas(types.Symbol("BTC-USD"), []ReplayDelta{
		{Symbol: "BTC-USD", Side: DeltaBid, Price: dec("100"), Size: dec("1.5"), Expected: 1},
		{Symbol: "BTC-USD", Side: DeltaAsk, Price: dec("102"), Size: dec("0.5"), Expected: 2},
		{Symbol: "BTC-USD", Side: DeltaBid, Price: dec("101"), Size: dec("2.0"), Expected: 2},
	})
	if err != nil {
		t.Fatalf("ReplayDeltas returned error: %v", err)
	}
	if mismatch == nil {
		t.Fatal("expected mismatch")
	}

	if mismatch.Step != 2 {
		t.Fatalf("expected mismatch at step 2, got %d", mismatch.Step)
	}
	if mismatch.Symbol != "BTC-USD" || mismatch.Side != DeltaAsk {
		t.Fatalf("unexpected mismatch market: %+v", mismatch)
	}
	if !mismatch.Price.Equal(dec("102")) || !mismatch.Size.Equal(dec("0.5")) {
		t.Fatalf("unexpected mismatch price/size: %+v", mismatch)
	}
	if mismatch.ExpectedDepth != 2 || mismatch.ActualDepth != 1 {
		t.Fatalf("unexpected mismatch depths: %+v", mismatch)
	}
}

func TestReplayMismatchSummaryIsCompactAndActionable(t *testing.T) {
	mismatch := ReplayMismatch{
		Step:          3,
		Symbol:        "ETH-USD",
		Side:          DeltaBid,
		Price:         dec("2500"),
		Size:          dec("4"),
		ExpectedDepth: 2,
		ActualDepth:   1,
	}
	summary := mismatch.Summary()
	for _, want := range []string{"step 3", "ETH-USD", "bid", "price=2500", "size=4", "expected_depth=2", "actual_depth=1"} {
		if !strings.Contains(summary, want) {
			t.Fatalf("summary %q missing %q", summary, want)
		}
	}
}
