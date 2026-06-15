// Package taskboard — identical spec across Python / Go / Rust.
package taskboard

import (
	"errors"
	"fmt"
	"sort"
)

type TaskStatus int

const (
	Todo TaskStatus = iota
	Done
)

// Typed sentinel errors. Go forces an explicit `if err != nil`, but does NOT
// force the caller to actually check the returned error (errcheck is a linter,
// not the compiler).
var (
	ErrEmptyTitle  = errors.New("title must not be empty")
	ErrBadPriority = errors.New("priority must be 1..5")
	ErrNotFound    = errors.New("task not found")
	ErrAlreadyDone = errors.New("task already done")
)

type Task struct {
	ID       int
	Title    string
	Priority int
	Status   TaskStatus
}

type TaskBoard struct {
	tasks  map[int]*Task
	nextID int
}

func New() *TaskBoard {
	return &TaskBoard{tasks: make(map[int]*Task), nextID: 1}
}

func trimSpace(s string) string {
	start, end := 0, len(s)
	for start < end && (s[start] == ' ' || s[start] == '\t' || s[start] == '\n') {
		start++
	}
	for end > start && (s[end-1] == ' ' || s[end-1] == '\t' || s[end-1] == '\n') {
		end--
	}
	return s[start:end]
}

func (b *TaskBoard) Add(title string, priority int) (int, error) {
	t := trimSpace(title)
	if t == "" {
		return 0, ErrEmptyTitle
	}
	if priority < 1 || priority > 5 {
		return 0, fmt.Errorf("%w: got %d", ErrBadPriority, priority)
	}
	task := &Task{ID: b.nextID, Title: t, Priority: priority, Status: Todo}
	b.tasks[task.ID] = task
	b.nextID++
	return task.ID, nil
}

func (b *TaskBoard) Complete(id int) error {
	task, ok := b.tasks[id]
	if !ok {
		return fmt.Errorf("%w: %d", ErrNotFound, id)
	}
	if task.Status == Done {
		return fmt.Errorf("%w: %d", ErrAlreadyDone, id)
	}
	task.Status = Done
	return nil
}

func (b *TaskBoard) Pending() []*Task {
	var todo []*Task
	for _, t := range b.tasks {
		if t.Status == Todo {
			todo = append(todo, t)
		}
	}
	sort.Slice(todo, func(i, j int) bool {
		if todo[i].Priority != todo[j].Priority {
			return todo[i].Priority > todo[j].Priority // highest first
		}
		return todo[i].ID < todo[j].ID
	})
	return todo
}

func (b *TaskBoard) Stats() (total, done, pending int) {
	total = len(b.tasks)
	for _, t := range b.tasks {
		if t.Status == Done {
			done++
		}
	}
	return total, done, total - done
}
