"""Step 4: Generate personalised outreach and follow-up emails."""

SUBJECT_TEMPLATE = "Tata AutoComp (TACO) — Automotive Component Solutions for {company}"

BODY_TEMPLATE = """\
Dear {first_name},

I came across your profile while researching component sourcing at {company}.

We're Tata AutoComp Systems (TACO) — a $2.2 Bn automotive components company and part of the Tata Group ($165 Bn conglomerate). With 61 manufacturing plants globally, IATF 16949 certification, and 25+ years serving all major global OEMs, we bring world-class scale and quality to the table.

Many North American OEMs are actively diversifying their supply chains through a 'China plus 1' strategy. India is emerging as a preferred alternative — with a mature automotive ecosystem powering the world's third-largest auto industry ($250 Bn+ in revenues).

The tariffs on Indian auto component exports to the US are now at 10%, making supplies highly competitive from India.

As {title} at {company}, I believe there is a strong case for exploring TACO's capabilities:

 ◆ Castings — Grey iron, ductile iron, SiMo & aluminum (HPDC, GDC, LPDC, investment & sand casting) from 50 gm to 500 kg
 ◆ Forgings — Steel, aluminum & copper, hot/warm/cold forging, 50 gm to 80 kg, closed & open die
 ◆ Machining — CNC/VMC/HMC with 5th-axis capability, turning, milling, grinding, hobbing
 ◆ Composites — Compression molding up to 3000T, parts from 200 gm to 50 kg
 ◆ HVAC & Thermal — Radiators, intercoolers, battery thermal management systems (BTMS), EGR coolers

Beyond these, TACO also manufactures EV components (busbars, battery packs, motors/inverters), plastics, stamping, seating systems, and more — backed by 105+ empaneled manufacturing associates for complete supply chain solutions.

Given your work in {industry}, I thought there might be value in a brief conversation about whether our capabilities align with any of your current or upcoming sourcing needs.

Happy to share our corporate presentation and detailed product capabilities if that would be useful.

Best regards,
Avinash Pullela
Tata AutoComp Systems (TACO)
avinash.pullela@citacinc.com\
"""

FOLLOWUP_SUBJECT_TEMPLATE = "Re: Tata AutoComp (TACO) — Automotive Component Solutions for {company}"

FOLLOWUP_BODY_TEMPLATE = """\
Dear {first_name},

I wanted to follow up on my earlier note about Tata AutoComp Systems (TACO).

TACO is a $2.2 Bn Tata Group company with 61 plants globally, supplying castings, forgings, machined parts, composites, HVAC/thermal systems, and EV components to major OEMs worldwide — all under IATF 16949 certification.

With India's tariff on auto component exports to the US now at 10%, we're hearing strong interest from North American manufacturers exploring supply chain diversification. I'd welcome a brief 20-minute call to see if there's a fit with your sourcing plans at {company}.

Would any time work for you in the coming week?

Best regards,
Avinash Pullela
Tata AutoComp Systems (TACO)
avinash.pullela@citacinc.com\
"""


def generate_email(contact: dict, company: str, industry: str) -> dict:
    first_name = contact.get("first_name") or contact["name"].split()[0]
    title = contact.get("title", "")
    subject = SUBJECT_TEMPLATE.format(company=company)
    body = BODY_TEMPLATE.format(
        first_name=first_name,
        company=company,
        title=title,
        industry=industry,
    )
    return {"subject": subject, "body": body, "to": contact["email"]}


def generate_followup(contact: dict, company: str, followup_count: int) -> dict:
    first_name = contact.get("first_name") or contact["name"].split()[0]
    subject = FOLLOWUP_SUBJECT_TEMPLATE.format(company=company)
    body = FOLLOWUP_BODY_TEMPLATE.format(first_name=first_name, company=company)
    return {"subject": subject, "body": body, "to": contact["email"]}
