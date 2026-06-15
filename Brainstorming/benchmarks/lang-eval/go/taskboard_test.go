package taskboard

import (
	"errors"
	"testing"
)

func TestAddValid(t *testing.T) {
	b := New()
	id1, err := b.Add("write spec", 3)
	if err != nil || id1 != 1 {
		t.Fatalf("got id=%d err=%v", id1, err)
	}
	id2, _ := b.Add("review", 5)
	if id2 != 2 {
		t.Fatalf("got id=%d", id2)
	}
}

func TestAddEmptyTitle(t *testing.T) {
	b := New()
	if _, err := b.Add("   ", 3); !errors.Is(err, ErrEmptyTitle) {
		t.Fatalf("expected ErrEmptyTitle, got %v", err)
	}
}

func TestAddBadPriority(t *testing.T) {
	b := New()
	if _, err := b.Add("x", 0); !errors.Is(err, ErrBadPriority) {
		t.Fatalf("expected ErrBadPriority, got %v", err)
	}
	if _, err := b.Add("x", 6); !errors.Is(err, ErrBadPriority) {
		t.Fatalf("expected ErrBadPriority, got %v", err)
	}
}

func TestCompleteOK(t *testing.T) {
	b := New()
	id, _ := b.Add("x", 2)
	if err := b.Complete(id); err != nil {
		t.Fatalf("unexpected err %v", err)
	}
	total, done, pending := b.Stats()
	if total != 1 || done != 1 || pending != 0 {
		t.Fatalf("stats = %d/%d/%d", total, done, pending)
	}
}

func TestCompleteNotFound(t *testing.T) {
	b := New()
	if err := b.Complete(99); !errors.Is(err, ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
}

func TestCompleteTwice(t *testing.T) {
	b := New()
	id, _ := b.Add("x", 2)
	_ = b.Complete(id)
	if err := b.Complete(id); !errors.Is(err, ErrAlreadyDone) {
		t.Fatalf("expected ErrAlreadyDone, got %v", err)
	}
}

func TestPendingOrdering(t *testing.T) {
	b := New()
	b.Add("low", 1)
	b.Add("high", 5)
	b.Add("mid", 3)
	got := b.Pending()
	want := []string{"high", "mid", "low"}
	for i, w := range want {
		if got[i].Title != w {
			t.Fatalf("pos %d: got %s want %s", i, got[i].Title, w)
		}
	}
}

func TestPendingExcludesDone(t *testing.T) {
	b := New()
	a, _ := b.Add("a", 2)
	b.Add("b", 4)
	_ = b.Complete(a)
	got := b.Pending()
	if len(got) != 1 || got[0].Title != "b" {
		t.Fatalf("expected [b], got %v", got)
	}
}

func TestStats(t *testing.T) {
	b := New()
	b.Add("a", 2)
	x, _ := b.Add("b", 4)
	_ = b.Complete(x)
	total, done, pending := b.Stats()
	if total != 2 || done != 1 || pending != 1 {
		t.Fatalf("stats = %d/%d/%d", total, done, pending)
	}
}
