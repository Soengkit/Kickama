package orderbook

import (
	"fmt"

	"github.com/shopspring/decimal"
	"github.com/tent-of-trials/market/types"
)

type DeltaSide string

const (
	DeltaBid DeltaSide = "bid"
	DeltaAsk DeltaSide = "ask"
)

type ReplayDelta struct {
	Symbol   types.Symbol    `json:"symbol"`
	Side     DeltaSide       `json:"side"`
	Price    decimal.Decimal `json:"price"`
	Size     decimal.Decimal `json:"size"`
	Expected int             `json:"expected_depth"`
}

type ReplayMismatch struct {
	Step          int             `json:"step"`
	Symbol        types.Symbol    `json:"symbol"`
	Side          DeltaSide       `json:"side"`
	Price         decimal.Decimal `json:"price"`
	Size          decimal.Decimal `json:"size"`
	ExpectedDepth int             `json:"expected_depth"`
	ActualDepth   int             `json:"actual_depth"`
}

func (m ReplayMismatch) Summary() string {
	return fmt.Sprintf(
		"delta step %d diverged for %s %s price=%s size=%s expected_depth=%d actual_depth=%d",
		m.Step,
		m.Symbol,
		m.Side,
		m.Price.String(),
		m.Size.String(),
		m.ExpectedDepth,
		m.ActualDepth,
	)
}

func ReplayDeltas(symbol types.Symbol, deltas []ReplayDelta) (*ReplayMismatch, error) {
	book := NewOrderBook(symbol, Config{MaxDepth: len(deltas) + 1})
	for i, delta := range deltas {
		if delta.Symbol != "" && delta.Symbol != symbol {
			mismatch := ReplayMismatch{
				Step:          i + 1,
				Symbol:        delta.Symbol,
				Side:          delta.Side,
				Price:         delta.Price,
				Size:          delta.Size,
				ExpectedDepth: delta.Expected,
				ActualDepth:   0,
			}
			return &mismatch, nil
		}

		order := &types.Order{
			Symbol:       symbol,
			Type:         types.Limit,
			Price:        delta.Price,
			Quantity:     delta.Size,
			RemainingQty: delta.Size,
		}
		if delta.Side == DeltaBid {
			order.Side = types.Buy
		} else {
			order.Side = types.Sell
		}

		if _, err := book.AddOrder(order); err != nil {
			return nil, err
		}

		actualDepth := len(book.GetBids())
		if delta.Side == DeltaAsk {
			actualDepth = len(book.GetAsks())
		}
		if actualDepth != delta.Expected {
			mismatch := ReplayMismatch{
				Step:          i + 1,
				Symbol:        symbol,
				Side:          delta.Side,
				Price:         delta.Price,
				Size:          delta.Size,
				ExpectedDepth: delta.Expected,
				ActualDepth:   actualDepth,
			}
			return &mismatch, nil
		}
	}
	return nil, nil
}
