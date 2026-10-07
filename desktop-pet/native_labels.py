"""Fit native pet labels to pixel-sized signs using the active Tk font metrics."""
def one_line(value):
    return ' '.join(str(value).split())


def elide(value, measure, width):
    text=one_line(value)
    if measure(text)<=width:
        return text
    suffix='…'
    if measure(suffix)>width:
        return ''
    low,high=0,len(text)
    while low<high:
        middle=(low+high+1)//2
        if measure(text[:middle]+suffix)<=width:low=middle
        else:high=middle-1
    return text[:low].rstrip()+suffix


def sign_text(label,status,summary,measure,width):
    detail=status+(' · '+one_line(summary) if summary else '')
    return elide(label,measure,width)+'\n'+elide(detail,measure,width)


def wrap_details(parts,measure,width,max_lines):
    """Bound hover content too, including long unbroken English identifiers."""
    lines=[]
    for part in parts:
        text=one_line(part)
        if not text:continue
        line=''
        for char in text:
            if line and measure(line+char)>width:
                lines.append(line);line=''
            line+=char
        if line:lines.append(line)
    if len(lines)>max_lines:
        lines=lines[:max_lines]
        lines[-1]=elide(lines[-1]+'…',measure,width)
    return '\n'.join(lines)
