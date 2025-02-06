CREATE TABLE reviewers ( 
  id SERIAL PRIMARY KEY, 
  name VARCHAR(255) NOT NULL 
);

CREATE TABLE quran_answers (
  id SERIAL PRIMARY KEY, 
  surah INT, 
  ayah INT, 
  question TEXT, 
  ansari_answer TEXT, 
  review_result VARCHAR(20) CHECK (review_result IN ('pending', 'approved', 'edited', 'disapproved')),
  reviewed_by INT, 
  reviewer_comment TEXT,
  final_answer TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (reviewed_by) REFERENCES reviewers(id)
);