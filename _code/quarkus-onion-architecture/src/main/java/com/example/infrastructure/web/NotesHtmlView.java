package com.example.infrastructure.web;

import com.example.domain.model.Note;

import java.util.List;

public final class NotesHtmlView {

    public static String render(List<Note> notes) {
        var sb = new StringBuilder();
        sb.append("<!DOCTYPE html>");
        sb.append("<html><head><meta charset=\"utf-8\"><title>Notes</title></head><body>");
        sb.append("<h1>Notes</h1>");
        sb.append("<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\">");
        sb.append("<thead><tr><th>id</th><th>title</th><th>body</th><th>created</th></tr></thead>");
        sb.append("<tbody>");
        for (var note : notes) {
            sb.append("<tr>");
            sb.append("<td>").append(note.id()).append("</td>");
            sb.append("<td>").append(escape(note.title())).append("</td>");
            sb.append("<td>").append(escape(note.body())).append("</td>");
            sb.append("<td>").append(note.createdAt()).append("</td>");
            sb.append("</tr>");
        }
        sb.append("</tbody></table>");
        sb.append("</body></html>");
        return sb.toString();
    }

    private static String escape(String value) {
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }
}
