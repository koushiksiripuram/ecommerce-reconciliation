interface PreviewTableProps {
  headers: string[]
  rows: Array<Record<string, string>>
}

/** Read-only peek at the first rows of the uploaded file. */
export function PreviewTable({ headers, rows }: PreviewTableProps) {
  return (
    <div className="card">
      <h2 className="card__title">Preview</h2>
      <p className="card__hint">
        First {rows.length} row{rows.length === 1 ? '' : 's'} of the uploaded file, exactly as
        read from the source.
      </p>

      {rows.length === 0 ? (
        <p className="empty-state">The file contains no data rows.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col" className="data-table__index">
                  #
                </th>
                {headers.map((header) => (
                  <th scope="col" key={header}>
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  <td className="data-table__index">{index + 1}</td>
                  {headers.map((header) => (
                    <td key={header}>{row[header] ?? ''}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
