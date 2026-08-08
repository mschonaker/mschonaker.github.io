package com.example.infrastructure.web;

import com.example.domain.model.NewNote;

import java.util.ArrayList;
import java.util.List;

public final class CsvNoteParser {

    public List<NewNote> parse(String csv) {
        var drafts = new ArrayList<NewNote>();
        for (var line : csv.lines().toList()) {
            if (line.isBlank()) {
                continue;
            }
            var parts = line.split(",", 2);
            var title = parts[0].trim();
            var body = parts.length > 1 ? parts[1].trim() : "";
            drafts.add(new NewNote(title, body));
        }
        return drafts;
    }
}
