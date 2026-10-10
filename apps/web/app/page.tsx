import Link from "next/link";
import { CaseForm } from "@/components/CaseForm";
import { Icon } from "@/components/Icon";
import { reportR5 } from "@/lib/fixtures/report-r5";

export default function HomePage() {
  return (
    <div className="page-container home-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR VIRTUAL INVESTMENT COMMITTEE</span>
          <h1>Look beyond the molecule.</h1>
          <p>
            Connect the biology to the investment thesis.
            <br className="desktop-break" /> Understand the evidence, the gaps,
            and what to ask next.
          </p>
        </div>
        <span className="heading-index">/ 001</span>
      </div>
      <div className="input-layout">
        <CaseForm />
        <aside className="input-aside">
          <Link href="/science-test">Test Science with real evidence</Link>
          <section className="workflow-card">
            <span className="eyebrow">FROM QUESTION TO CONVICTION</span>
            <div
              className="orbit-illustration"
              aria-hidden="true"
            >
              <div className="orbit orbit-one" />
              <div className="orbit orbit-two" />
              <span className="orbit-node node-one" />
              <span className="orbit-node node-two" />
              <span className="orbit-node node-three" />
              <span className="orbit-centre">
                <Icon
                  name="flask"
                  size={30}
                />
              </span>
            </div>
            <h2>
              Every conclusion.
              <br />A path to its evidence.
            </h2>
            <p>
              A committee view of the science, clinical development, and
              investment case.
            </p>
            <ol className="workflow-list">
              <li>
                <span>01</span>
                <div>
                  <strong>Frame the thesis</strong>
                  <small>Indication, target, and assessment scope</small>
                </div>
              </li>
              <li>
                <span>02</span>
                <div>
                  <strong>Examine the evidence</strong>
                  <small>Supporting findings and contradictions</small>
                </div>
              </li>
              <li>
                <span>03</span>
                <div>
                  <strong>Understand the decision</strong>
                  <small>Conditions, risks, and diligence questions</small>
                </div>
              </li>
            </ol>
          </section>
          <Link
            href="/cases/sample"
            className="example-link"
          >
            <span className="example-icon">
              <Icon
                name="book"
                size={23}
              />
            </span>
            <div>
              <span className="eyebrow">TAKE A LOOK FIRST</span>
              <strong>Explore a fictional report</strong>
              <small>
                {reportR5.sections.length} sections · {reportR5.roles.length}{" "}
                perspectives
              </small>
            </div>
            <Icon
              name="arrow"
              size={18}
            />
          </Link>
        </aside>
      </div>
      <div className="principles">
        <div>
          <Icon
            name="file"
            size={19}
          />
          <span>Traceable conclusions</span>
        </div>
        <div>
          <Icon
            name="warning"
            size={19}
          />
          <span>Unknowns stay visible</span>
        </div>
        <div>
          <Icon
            name="layers"
            size={19}
          />
          <span>Perspectives, with context</span>
        </div>
      </div>
    </div>
  );
}
