//! TaskBoard domain library — identical spec across Python / Go / Rust.
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaskStatus {
    Todo,
    Done,
}

/// Domain errors as an algebraic type. The compiler FORCES every caller to
/// handle the `Result` (`#[must_use]`) and forces `match` to be exhaustive.
#[derive(Debug, PartialEq, Eq)]
pub enum TaskError {
    EmptyTitle,
    BadPriority(i32),
    NotFound(u32),
    AlreadyDone(u32),
}

#[derive(Debug, Clone)]
pub struct Task {
    pub id: u32,
    pub title: String,
    pub priority: i32,
    pub status: TaskStatus,
}

#[derive(Default)]
pub struct TaskBoard {
    tasks: HashMap<u32, Task>,
    next_id: u32,
}

impl TaskBoard {
    pub fn new() -> Self {
        TaskBoard {
            tasks: HashMap::new(),
            next_id: 1,
        }
    }

    pub fn add(&mut self, title: &str, priority: i32) -> Result<u32, TaskError> {
        let trimmed = title.trim();
        if trimmed.is_empty() {
            return Err(TaskError::EmptyTitle);
        }
        if !(1..=5).contains(&priority) {
            return Err(TaskError::BadPriority(priority));
        }
        let id = self.next_id;
        self.tasks.insert(
            id,
            Task {
                id,
                title: trimmed.to_string(),
                priority,
                status: TaskStatus::Todo,
            },
        );
        self.next_id += 1;
        Ok(id)
    }

    pub fn complete(&mut self, id: u32) -> Result<(), TaskError> {
        let task = self.tasks.get_mut(&id).ok_or(TaskError::NotFound(id))?;
        match task.status {
            TaskStatus::Done => Err(TaskError::AlreadyDone(id)),
            TaskStatus::Todo => {
                task.status = TaskStatus::Done;
                Ok(())
            }
        }
    }

    pub fn pending(&self) -> Vec<&Task> {
        let mut todo: Vec<&Task> = self
            .tasks
            .values()
            .filter(|t| t.status == TaskStatus::Todo)
            .collect();
        // highest priority first, then by id ascending
        todo.sort_by(|a, b| b.priority.cmp(&a.priority).then(a.id.cmp(&b.id)));
        todo
    }

    pub fn stats(&self) -> (usize, usize, usize) {
        let total = self.tasks.len();
        let done = self
            .tasks
            .values()
            .filter(|t| t.status == TaskStatus::Done)
            .count();
        (total, done, total - done)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add_valid() {
        let mut b = TaskBoard::new();
        assert_eq!(b.add("write spec", 3), Ok(1));
        assert_eq!(b.add("review", 5), Ok(2));
    }

    #[test]
    fn add_empty_title() {
        let mut b = TaskBoard::new();
        assert_eq!(b.add("   ", 3), Err(TaskError::EmptyTitle));
    }

    #[test]
    fn add_bad_priority() {
        let mut b = TaskBoard::new();
        assert_eq!(b.add("x", 0), Err(TaskError::BadPriority(0)));
        assert_eq!(b.add("x", 6), Err(TaskError::BadPriority(6)));
    }

    #[test]
    fn complete_ok() {
        let mut b = TaskBoard::new();
        let id = b.add("x", 2).unwrap();
        assert_eq!(b.complete(id), Ok(()));
        assert_eq!(b.stats(), (1, 1, 0));
    }

    #[test]
    fn complete_not_found() {
        let mut b = TaskBoard::new();
        assert_eq!(b.complete(99), Err(TaskError::NotFound(99)));
    }

    #[test]
    fn complete_twice() {
        let mut b = TaskBoard::new();
        let id = b.add("x", 2).unwrap();
        b.complete(id).unwrap();
        assert_eq!(b.complete(id), Err(TaskError::AlreadyDone(id)));
    }

    #[test]
    fn pending_ordering() {
        let mut b = TaskBoard::new();
        b.add("low", 1).unwrap();
        b.add("high", 5).unwrap();
        b.add("mid", 3).unwrap();
        let order: Vec<&str> = b.pending().iter().map(|t| t.title.as_str()).collect();
        assert_eq!(order, vec!["high", "mid", "low"]);
    }

    #[test]
    fn pending_excludes_done() {
        let mut b = TaskBoard::new();
        let a = b.add("a", 2).unwrap();
        b.add("b", 4).unwrap();
        b.complete(a).unwrap();
        let titles: Vec<&str> = b.pending().iter().map(|t| t.title.as_str()).collect();
        assert_eq!(titles, vec!["b"]);
    }

    #[test]
    fn stats() {
        let mut b = TaskBoard::new();
        b.add("a", 2).unwrap();
        let x = b.add("b", 4).unwrap();
        b.complete(x).unwrap();
        assert_eq!(b.stats(), (2, 1, 1));
    }
}
