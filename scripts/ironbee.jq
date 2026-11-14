# The rules the workflow's scripts apply to an event and to GitHub's and IronBee's answers, as jq functions over data
# (`jq -L scripts 'include "ironbee"; ...'`). Each mirrors the runner's own rule of the same name, so that a job without
# the image decides as the image would: the mention and the retract word, a bot's comment, our marker, a fork, who
# counts on a thread, and the registration's answer read leniently. Written for jq 1.6 and later.

def obj: if type == "object" then . else {} end;

# A text on one line: whitespace runs as one space, at most 300 characters.
def one_line: if . == null then "" elif type == "string" then . else tojson end | [splits("\\s+")] | map(select(length > 0)) | join(" ") | .[0:300];

def rx_quote: gsub("(?<c>[\\\\^$.|?*+()\\[\\]{}/-])"; "\\\(.c)");

# One of the names (`@ironbee-ai`, `@<slug>`) as a whole word: the character before it none of ASCII letters, digits,
# `_`, `/`, `-`, the one after none of ASCII letters, digits, `_`, `-`. ASCII case is ignored and no other: the input is
# lowered by ascii_downcase, which leaves every other character as it is.
def mention_rx($names): "(?<![a-z0-9_/-])(?:" + ([$names[] | ascii_downcase | rx_quote] | join("|")) + ")(?![a-z0-9_-])";

# Whether a comment's body addresses us.
def addressed($names): ascii_downcase | test(mention_rx($names));

# Whether it asks for a retract: the word `retract` after the first mention, its edges no ASCII letter, digit or `_`.
def asks_retract($names):
  ascii_downcase | [capture(mention_rx($names) + "(?<rest>[\\s\\S]*)")]
  | if length == 0 then false else (.[0].rest | test("(?<![a-z0-9_])retract(?![a-z0-9_])")) end;

# Our marker, a hidden line `<!-- ironbee <id> -->`, on a line that quotes nothing: a reply quoting ours is not ours.
def has_marker:
  [splits("\r\n|[\n\r\u000b\u000c\u001c\u001d\u001e\u0085  ]")]
  | any(.[]; (sub("^\\s+"; "") | startswith(">") | not) and test("<!-- ironbee .+? -->"));

# A text of ours: written by our identity, with our marker.
def ours_post($login): ((.user.login // "") == $login) and ((.body // "") | has_marker);

# A review of ours on that commit.
def ours_review($login; $head): .commit_id == $head and ours_post($login);

# A check run of ours: the gate's name, written by our identity's App.
def ours_check($slug): .name == "IronBee review" and (((.app.slug // "") | ascii_downcase) == ($slug | ascii_downcase));

# A pull request from a fork: its head in another repository, or in one deleted since.
def forked:
  ((.head.repo.full_name // "") | ascii_downcase) as $h | ((.base.repo.full_name // "") | ascii_downcase) as $b
  | $h == "" or $b == "" or $h != $b;

# A comment a bot wrote, our own identity's included.
def bot_comment($login):
  (.comment.user.type == "Bot") or (.sender.type == "Bot")
  or (((.comment.user.login // "") | ascii_downcase) == ($login | ascii_downcase));

# Whose word counts on a thread: the pull request's author, or an owner, a member or a collaborator of the repository.
def counts:
  (.comment.author_association // "") as $a | (.comment.user.login // "") as $l
  | (["OWNER", "MEMBER", "COLLABORATOR"] | map(. == $a) | any) or ($l != "" and $l == (.pull_request.user.login // ""));

# A permission that pushes.
def writer: . == "admin" or . == "maintain" or . == "write";

def count_ok: type == "number" and . == floor and . >= 0 and . <= 9007199254740991;

def version_ok: type == "string" and test("^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(\\.(0|[1-9][0-9]*))?$");

# A calendar day `YYYY-MM-DD` as days since 1970-01-01 (UTC), or null for anything else.
def day_number:
  if type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$") then
    . as $text | (try (strptime("%Y-%m-%d") | mktime) catch null) as $t
    | if $t != null and ($t | gmtime | strftime("%Y-%m-%d")) == $text then ($t / 86400 | floor) else null end
  else null end;

# The job log's warnings for an answer's licence and version standing, one line each. None names a count, a limit or
# an end date of the contract: a public repository's log is public. A version's own last day and the version to move to
# are named.
def warnings($version; $today):
  (.licence | obj) as $l | ($l.developers | obj) as $d | (.runner | obj) as $r
  | (if ($d.used | count_ok) and ($d.limit | count_ok) and $d.used > $d.limit
     then "warning: this account has more developers this month than its licence covers; reviews go on, and IronBee will be in touch"
     else empty end),
    (($l.endsAt | day_number) as $end
     | if $end != null and ($end - $today) >= 0 and ($end - $today) < 14
       then "warning: the licence for IronBee's self-hosted review ends soon; renew it to keep pull requests reviewed"
       else empty end),
    (($r.supportedUntil | day_number) as $until
     | if $until != null
       then "warning: runner \($version) is served until \($r.supportedUntil); move the workflow to "
            + (if ($r.moveTo | version_ok) then "\($r.moveTo) before then" else "a supported version before then" end)
       else empty end);

def refusals: {
  "SELF_HOSTED_RUNNER_NOT_ENABLED": "IronBee's self-hosted review is not enabled for this account; contact IronBee.",
  "SELF_HOSTED_RUNNER_SUSPENDED": "IronBee's reviews are suspended for this account; contact IronBee.",
  "SELF_HOSTED_RUNNER_LICENCE_ENDED": "The licence for IronBee's self-hosted review has ended; contact IronBee to renew it.",
  "REPOSITORY_REVIEWED_BY_CLOUD": "IronBee's cloud reviews this repository; turn its code review off in the console before the runner reviews it."
};

# A refused call's answer: {code, sentence}. A code this release does not know is a refusal shown with its own text.
def refusal($status):
  (if type == "object" then .error else null end | obj) as $e
  | (if ($e.code | type) == "string" and ($e.code | length) > 0 then $e.code else "HTTP_\($status)" end) as $code
  | ($e.message | one_line | if . == "" then "HTTP \($status)" else . end) as $message
  | ($e.details | obj) as $d
  | {code: $code,
     sentence: (if $code == "RUNNER_VERSION_UNSUPPORTED" then
                  "This version of the IronBee runner is no longer served; move the workflow to "
                  + (if ($d.moveTo | version_ok) then $d.moveTo else "a supported version" end) + "."
                  + ($d.reason | one_line | if . == "" then "" else " Reason: \(.)" end)
                else (refusals[$code] // $message) end)};

def no_project_cases: ["project_limit", "project_archived", "name_taken"];

# The registration's answer: {project: {id, created} | null, why: the case that left the repository without one | null,
# dropped: an unknown case, for the log | null}.
def registered:
  (if (.project | type) == "object" and (.project.id | type) == "string" then
     {id: (.project.id | one_line),
      created: (.project.created | if . == null or . == false or . == 0 or . == "" or . == [] or . == {} then false else true end)}
   else null end) as $p
  | (if $p == null then .noProject else null end) as $why
  | {project: $p,
     why: (if $why != null and (no_project_cases | index([$why])) != null then $why else null end),
     dropped: (if $why != null and (no_project_cases | index([$why])) == null then ($why | one_line | .[0:60]) else null end)};
