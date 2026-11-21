
class Tags:
    Authorization = "Authorization"
    Users = "Users"
    Tags = "Tags"
    Locations = "Locations"
    Projects = "Projects"
    Ideas = "Ideas"
    Matters = "Matters"
    Operator = "Operator"
    Conversations = "Conversations"
    Statistics = "Statistics"


tags_metadata = [
    {
        "name": Tags.Authorization,
        "description": "Operations with authorization, login, logout.",
    },
    {
        "name": Tags.Users,
        "description": "Operations with users. Managing other users requires the admin role.",
    },
    {
        "name": Tags.Tags,
        "description": "Admin-defined tags and their subtags used to classify conversations and projects. Reading is public.",
    },
    {
        "name": Tags.Locations,
        "description": "Podkarpackie administrative units (voivodeship, counties, municipalities) "
                       "and their boundaries as GeoJSON for OpenStreetMap maps. Public.",
    },
    {
        "name": Tags.Ideas,
        "description": "Idea creator cards (fiszka) submitted by logged-in users and reviewed by the admin. "
                       "Published ideas are public.",
    },
    {
        "name": Tags.Matters,
        "description": "User-owned matters (Moje sprawy): Markdown drafts with compare-and-swap edits, "
                       "chat thread link and PDF export.",
    },
    {
        "name": Tags.Operator,
        "description": "Operator (PCI) staff contacts, the public contact form and shared document helpers (PDF from Markdown).",
    },
    {
        "name": Tags.Projects,
        "description": "Innovation projects with PDFs, links, participants by location "
                       "and map points. Reading published projects is public; managing them requires the admin role.",
    },
    {
        "name": Tags.Conversations,
        "description": "Chat with the Radar assistant: answers, automatic tags and recommended projects. "
                       "Chatting is public (anonymous conversations keep no message text); "
                       "saved history, renaming, deleting and tag edits require login.",
    },
    {
        "name": Tags.Statistics,
        "description": "Page view tracking (public) and usage, tag, trend, project and location "
                       "statistics for the admin, computed from the application tables.",
    },
]
